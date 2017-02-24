import numpy as np
import data_transforms
import data_iterators
import pathfinder
import lasagne as nn
from collections import namedtuple
from functools import partial
import lasagne.layers.dnn as dnn
import theano.tensor as T
import utils

restart_from_save = None
rng = np.random.RandomState(42)

# transformations
p_transform = {'patch_size': (64, 64, 64),
               'mm_patch_size': (64, 64, 64),
               'pixel_spacing': (1., 1., 1.)
               }
p_transform_augment = {
    'translation_range_z': [-16, 16],
    'translation_range_y': [-16, 16],
    'translation_range_x': [-16, 16],
    'rotation_range_z': [-180, 180],
    'rotation_range_y': [-180, 180],
    'rotation_range_x': [-180, 180]
}


# data preparation function
def data_prep_function(data, patch_center, luna_annotations, pixel_spacing, luna_origin, p_transform,
                       p_transform_augment, **kwargs):
    x, patch_annotation_tf, annotations_tf = data_transforms.transform_patch3d(data=data,
                                                                               luna_annotations=luna_annotations,
                                                                               patch_center=patch_center,
                                                                               p_transform=p_transform,
                                                                               p_transform_augment=p_transform_augment,
                                                                               pixel_spacing=pixel_spacing,
                                                                               luna_origin=luna_origin)
    x = data_transforms.hu2normHU(x)
    y = data_transforms.make_3d_mask_from_annotations(img_shape=x.shape, annotations=annotations_tf, shape='sphere')
    return x, y


data_prep_function_train = partial(data_prep_function, p_transform_augment=p_transform_augment, p_transform=p_transform)
data_prep_function_valid = partial(data_prep_function, p_transform_augment=None, p_transform=p_transform)

# data iterators
batch_size = 4
nbatches_chunk = 8
chunk_size = batch_size * nbatches_chunk

train_valid_ids = utils.load_pkl(pathfinder.LUNA_VALIDATION_SPLIT_PATH)
train_pids, valid_pids = train_valid_ids['train'], train_valid_ids['valid']

train_data_iterator = data_iterators.PatchPositiveLunaDataGenerator(data_path=pathfinder.LUNA_DATA_PATH,
                                                                    batch_size=chunk_size,
                                                                    transform_params=p_transform,
                                                                    data_prep_fun=data_prep_function_train,
                                                                    rng=rng,
                                                                    patient_ids=train_pids,
                                                                    full_batch=True, random=True, infinite=True)

valid_data_iterator = data_iterators.ValidPatchPositiveLunaDataGenerator(data_path=pathfinder.LUNA_DATA_PATH,
                                                                         transform_params=p_transform,
                                                                         data_prep_fun=data_prep_function_valid,
                                                                         patient_ids=valid_pids)
nchunks_per_epoch = train_data_iterator.nsamples / chunk_size
max_nchunks = nchunks_per_epoch * 30

validate_every = int(2. * nchunks_per_epoch)
save_every = int(0.5 * nchunks_per_epoch)

learning_rate_schedule = {
    0: 1e-5,
    int(max_nchunks * 0.4): 5e-6,
    int(max_nchunks * 0.5): 3e-6,
    int(max_nchunks * 0.6): 2e-6,
    int(max_nchunks * 0.85): 1e-6,
    int(max_nchunks * 0.95): 5e-7
}

# model
conv3d = partial(dnn.Conv3DDNNLayer,
                 filter_size=3,
                 pad='valid',
                 W=nn.init.Orthogonal('relu'),
                 b=nn.init.Constant(0.0),
                 nonlinearity=nn.nonlinearities.identity)

max_pool3d = partial(dnn.MaxPool3DDNNLayer,
                     pool_size=2)


def build_model():
    l_in = nn.layers.InputLayer((None, 1,) + p_transform['patch_size'])
    l_target = nn.layers.InputLayer((None, 1,) + p_transform['patch_size'])

    net = {}
    base_n_filters = 128
    net['contr_1_1'] = conv3d(l_in, base_n_filters)
    net['contr_1_1'] = nn.layers.ParametricRectifierLayer(net['contr_1_1'])
    net['contr_1_2'] = conv3d(net['contr_1_1'], base_n_filters)
    net['contr_1_2'] = nn.layers.ParametricRectifierLayer(net['contr_1_2'])
    net['contr_1_3'] = conv3d(net['contr_1_2'], base_n_filters)
    net['contr_1_3'] = nn.layers.ParametricRectifierLayer(net['contr_1_3'])
    net['pool1'] = max_pool3d(net['contr_1_3'])

    net['encode_1'] = conv3d(net['pool1'], base_n_filters)
    net['encode_1'] = nn.layers.ParametricRectifierLayer(net['encode_1'])
    net['encode_2'] = conv3d(net['encode_1'], base_n_filters)
    net['encode_2'] = nn.layers.ParametricRectifierLayer(net['encode_2'])
    net['encode_3'] = conv3d(net['encode_2'], base_n_filters)
    net['encode_3'] = nn.layers.ParametricRectifierLayer(net['encode_3'])
    net['encode_4'] = conv3d(net['encode_3'], base_n_filters)
    net['encode_4'] = nn.layers.ParametricRectifierLayer(net['encode_4'])

    net['dropout_1'] = nn.layers.DropoutLayer(net['encode_4'])

    net['upscale1'] = nn.layers.Upscale3DLayer(net['dropout_1'], 2)

    net['concat1'] = nn.layers.ConcatLayer([net['upscale1'], net['contr_1_3']],
                                           cropping=(None, None, "center", "center", "center"))
    net['expand_1_1'] = conv3d(net['concat1'], 2 * base_n_filters)
    net['expand_1_1'] = nn.layers.ParametricRectifierLayer(net['expand_1_1'])
    net['expand_1_2'] = conv3d(net['expand_1_1'], 2 * base_n_filters)
    net['expand_1_2'] = nn.layers.ParametricRectifierLayer(net['expand_1_2'])
    net['expand_1_3'] = conv3d(net['expand_1_2'], base_n_filters)
    net['expand_1_3'] = nn.layers.ParametricRectifierLayer(net['expand_1_3'])

    l_out = dnn.Conv3DDNNLayer(net['expand_1_3'], num_filters=1,
                               filter_size=1,
                               nonlinearity=nn.nonlinearities.sigmoid)
    return namedtuple('Model', ['l_in', 'l_out', 'l_target'])(l_in, l_out, l_target)


def build_objective(model, deterministic=False, epsilon=1e-12):
    network_predictions = nn.layers.get_output(model.l_out, deterministic=deterministic)
    target_values = nn.layers.get_output(model.l_target)
    network_predictions, target_values = nn.layers.merge.autocrop([network_predictions, target_values],
                                                                  [None, None, 'center', 'center', 'center'])
    y_true_f = target_values
    y_pred_f = network_predictions

    intersection = T.sum(y_true_f * y_pred_f)
    dice = (2 * intersection + epsilon) / (T.sum(y_true_f) + T.sum(y_pred_f) + epsilon)
    return -1. * dice


def build_updates(train_loss, model, learning_rate):
    updates = nn.updates.adam(train_loss, nn.layers.get_all_params(model.l_out), learning_rate)
    return updates
