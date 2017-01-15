import numpy as np

rng = np.random.RandomState(42)
patch_size = (64, 64)
mm_patch_size = (128, 128)
train_transformation_params = {
    'patch_size': patch_size,
    'mm_patch_size': mm_patch_size,
    'rotation_range': (-10, 10),
    'mask_roi': True,
    'translation_range_x': (-2, 2),
    'translation_range_y': (-2, 2),
    'shear_range': (0, 0),
    'roi_scale_range': (1., 1.),
    'do_flip': (True, True),
    'zoom_range': (1 / 1.1, 1.1),
    'sequence_shift': False
}

valid_transformation_params = {
    'patch_size': patch_size,
    'mm_patch_size': mm_patch_size,
    'mask_roi': True
}