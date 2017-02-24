import glob
import os
import sys
import numpy as np
import blobs_detection
import pathfinder
import utils
import utils_lung
from configuration import set_configuration
import data_transforms

if len(sys.argv) < 2:
    sys.exit("Usage: evaluate_luna_scan.py <configuration_name>")

config_name = sys.argv[1]
# set_configuration('configs_luna_scan', config_name)

# predictions path
predictions_dir = utils.get_dir_path('model-predictions', pathfinder.METADATA_PATH)
# blobs_dir = '/mnt/storage/metadata/dsb3/model-predictions/ikorshun/luna_s_p4'
# blobs_dir = '/mnt/storage/metadata/dsb3/model-predictions/ikorshun/luna_s_p5_pixelnorm'
outputs_path = predictions_dir + '/%s/' % config_name

files = os.listdir(outputs_path)
# x_files = sorted(glob.glob(outputs_path + '/in_*.npy'))
y_files = sorted(glob.glob(outputs_path + '/tgt_*.npy'))
pred_files = sorted(glob.glob(outputs_path + '/pred_*.npy'))
blob_files = sorted(glob.glob(blobs_dir + '/blob_*.npy'))
# print blob_files

tp = 0
n_pos = 0
n_blobs = 0
for yf, bf in zip(y_files, blob_files):
    annotations_scan = utils.load_np(yf)

    pid = utils_lung.luna_extract_pid(yf, '.npy').replace('tgt_', '')
    assert pid in yf
    assert pid in bf
    print pid

    print 'loading blobs'
    blobs = utils.load_np(bf)
    n_blobs += len(blobs)

    for zyxd in annotations_scan:
        n_pos += 1
        r = zyxd[-1] / 2.
        distance2 = ((zyxd[0] - blobs[:, 0]) ** 2
                     + (zyxd[1] - blobs[:, 1]) ** 2
                     + (zyxd[2] - blobs[:, 2]) ** 2)
        blob_idx = np.argmin(distance2)
        blob = blobs[blob_idx]
        print 'node', zyxd
        print 'closest blob', blob, blob_idx
        if distance2[blob_idx] < r ** 2:
            tp += 1
            print 'detected!!!'
        else:
            print 'not detected'

print 'TP', tp
print 'n blobs', n_blobs
print n_pos
