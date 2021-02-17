from tifffile import imread, imsave
import numpy as np
import random
import os
import torch
import torch.utils.data
import ImageTools
import cv2



LOW_RES = 16  # the low resolution number of pixels LOW_RESxLOW_RES
HIGH_RES = 64  # the high resolution number of pixels HIGH_RESxHIGH_RES
N_SAMPLES = 10000
CROP = 4  # crop pixels in each dimension when choosing train slices

if os.getcwd().endswith('code'):
    os.chdir('..')  # current directory from /SuperRes/code to SuperRes/
TIF_IMAGE = 'data/NMC.tif'


class BatchMaker:
    """
    Makes and saves training and test batch images.
    """

    def __init__(self, device, path=TIF_IMAGE,
                 low_res=LOW_RES, high_res=HIGH_RES, crop=True):
        """
        :param path: the path of the tif file (TODO make it more general)
        :param device: the device that the image is on.
        :param low_res: the low resolution of the 2d image.
        :param high_res: the high resolution of the 2d image.
        :param crop: if to crop the image at the edges
        """
        self.path = path
        self.device = device
        self.im_3d = imread(path)
        self.phases = np.unique(self.im_3d)  # the unique values in image
        self.min_d = min(self.im_3d.shape)  # the minimal dimension
        # crop the image in the edges:
        if crop:
            self.im_3d = self.im_3d[CROP:self.min_d-CROP, CROP:self.min_d-CROP,
                                    CROP:self.min_d-CROP]
            self.min_d = self.min_d - 2*CROP  # update the min dimension
        self.im_ohe = ImageTools.one_hot_encoding(self.im_3d, self.phases)
        self.low_res = low_res
        self.high_res = high_res

    # def save_batches(self):
    #     self.ohe_d_train = torch.FloatTensor(self.ohe_d_train)
    #     dataset = torch.utils.data.TensorDataset(self.ohe_d_train)
    #     torch.save(dataset, 'data/d_train.pth')
    #     self.ohe_g_train = torch.FloatTensor(self.ohe_g_train)
    #     dataset = torch.utils.data.TensorDataset(self.ohe_g_train)
    #     torch.save(dataset, 'data/g_train.pth')

    def random_batch(self, batch_size, dim_chosen):
        """
        :return: A batch of high resolution images,
        along the dimension chosen (0->x,1->y,2->z) in the 3d tif image.
        """
        res = np.zeros((batch_size, len(self.phases), self.high_res,
                        self.high_res))
        for i in range(batch_size):
            res[i, :, :, :] = self.generate_a_random_image(dim_chosen)
        # return a torch tensor:
        return torch.FloatTensor(res).to(self.device)

    def generate_a_random_image(self, dim_chosen):
        """
        :param dim_chosen: the dimension chosen for the slice
        :return: A random image of size res from the dimension chosen of the
        image.
        """
        slice_chosen = random.randint(0, self.min_d - 1)  # the
        # slice chosen
        lim_pix = self.min_d - self.high_res  # the maximum pixel to start with
        # the starting pixels of the other dimensions:
        pix1 = random.randint(0, lim_pix)
        pix2 = random.randint(0, lim_pix)
        if dim_chosen == 0:
            res_image = self.im_ohe[:, slice_chosen, pix1:pix1 + self.high_res,
                                    pix2:pix2 + self.high_res]
        elif dim_chosen == 1:
            res_image = self.im_ohe[:, pix1:pix1 + self.high_res, slice_chosen,
                                    pix2:pix2 + self.high_res]
        else:  # dim_chosen == 2
            res_image = self.im_ohe[:, pix1:pix1 + self.high_res, pix2:pix2 +
                                    self.high_res, slice_chosen]
        return res_image

    def all_image_batch(self, dim, all_image=False):
        """
        :param dim: the dimension to slice the images.
        :param all_image: if True, all image is chosen, if False,
        only middle part of the image at given dimension is chosen with high
        resolution
        :param device: the device that G is on.
        :return: a 3d image with dimension Depthx3xWidthxHeight
        """
        start = 0  # the start pixel
        resolution = self.min_d
        if not all_image:
            # s.t. the image will be in the middle
            start = (self.min_d - self.high_res) // 2
            resolution = self.high_res
        if dim == 0:
            res = self.im_ohe[:, :, start:start + resolution, start:start +
                              resolution]
            res = res.transpose(1, 0, 2, 3)
        if dim == 1:
            res = self.im_ohe[:,start:start + resolution, :, start:start +
                              resolution]
            res = res.transpose(2, 0, 1, 3)
        else:  # dim == 2:
            res = self.im_ohe[:, start:start + resolution, start:start +
                              resolution, :]
            res = res.transpose(3, 0, 1, 2)
        return torch.FloatTensor(res).to(self.device)


def main():
    BM = BatchMaker('cpu')
    z_slices = BM.random_batch(64, 1)
    print(BM.im_ohe.shape)


if __name__ == '__main__':
    main()
