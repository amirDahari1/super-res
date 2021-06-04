from tifffile import imread, imsave
import numpy as np
import random
import os
import torch
import torch.utils.data
import ImageTools
import LearnTools
import math
from PIL import Image
import matplotlib.pyplot as plt

perms = [[1, 2, 3], [2, 1, 3], [3, 1, 2]]  # permutations for a 4d array.
perms_3d = np.array(perms) + 1 # permutations for a 5d array.
CROP = 4  # crop pixels in each dimension when choosing train slices
# LOW_L_3D = 45  # length of low resolution 3d
HIGH_L_3D = 64  # length of high resolution 3d

if os.getcwd().endswith('code'):
    os.chdir('..')  # current directory from /SuperRes/code to SuperRes/
NMC_PATH = 'data/NMC.tif'
SOFC_CATHODE_PATH = 'netl-sofc-cathode-segmented.tif'


class BatchMaker:
    """
    Makes and saves training and test batch images.
    """

    def __init__(self, device, to_low_idx=False, path=NMC_PATH, sf=4, dims=3,
                 stack=True, crop=False, down_sample=False,
                 low_res=False, rot_and_mir=True, squash=False):
        """
        :param device: the device that the image is on.
        :param to_low_idx: the indices of the phases to be down-sampled.
        :param path: the path of the tif file (TODO make it more general)
        :param sf: the scale factor between low and high res.
        :param dims: number of dimensions for the batches (2 or 3)
        :param stack: if the data is a stack of 2D images
        :param crop: if to crop the image at the edges.
        :param down_sample: whether to down-sample the data or not.
        :param rot_and_mir: if True, the stack of 2D images will rotate and
        mirror for another 8 configurations
        :param squash: whether to squash all phases (other than pore) to one phase.
        """
        # down-sample parameters:
        self.down_sample, self.to_low_idx, self.squash = down_sample, \
                                                         to_low_idx, squash
        self.scale_factor = sf
        self.path = path
        self.dims = dims  # if G is 3D to 3D or 2D to 2D
        self.device = device
        self.stack = stack
        self.im = imread(path)
        if rot_and_mir:
            self.rotate_and_mirror()
        self.dim_im = len(self.im.shape)  # the dimension of the image
        self.phases = np.unique(self.im)  # the unique values in image
        if crop:  # crop the image in the edges:
            if self.dim_im == 3:
                self.im = self.im[CROP:-CROP, CROP:-CROP, CROP:-CROP]
            else:
                self.im = self.im[CROP:-CROP, CROP:-CROP]
        self.im = ImageTools.one_hot_encoding(self.im, self.phases)
        self.high_l = HIGH_L_3D
        if low_res:
            self.high_l = int(HIGH_L_3D/self.scale_factor)
        if self.dims == 2:
            self.high_l = self.high_l*2

    def down_sample_im(self, image):
        """
        :return: a down-sample image of the high resolution image for the input
        of G.
        """
        material_low_res = LearnTools.down_sample(torch.FloatTensor(
            image).to(self.device), self.to_low_idx, self.scale_factor,
                                                  self.dims, self.squash)
        # add a tiny bit of noise for all the 0.5 voxels so there will not
        # be a bias in either way:
        material_low_res += (torch.rand(material_low_res.size(),
                                        device=self.device)-0.5)/100
        # threshold at 0.5:
        material_low_res = torch.where(material_low_res > 0.5, 1., 0.)
        # make the pore channel:
        if self.squash:  # material_low_res already in one channel
            pore_phase = torch.ones(size=material_low_res.size(),
                                    device=self.device) - material_low_res
        else:  # material_low_res can be in multiple channels
            sum_of_low_res = torch.sum(material_low_res, dim=1).unsqueeze(
                dim=1)
            pore_phase = torch.ones(size=sum_of_low_res.size(),
                                    device=self.device) - sum_of_low_res
        # concat pore and material:
        return torch.cat((pore_phase, material_low_res), dim=1).squeeze(0)

    def rotate_and_mirror(self):
        """
        Given a stack of 2D images, in the form of num_images X width X heigth
        return a num_images*8 X width X height stack, with all 8 different
        90deg rotations and mirrors of the images.
        """
        num_ims = self.im.shape[0]
        flip_im = np.flip(self.im, -1)
        res = np.zeros((num_ims*8, *self.im.shape[1:]), dtype=self.im.dtype)
        for k in np.arange(4):  # for each 90 deg rotation
            first_i, second_i = 2*k*num_ims, (2*k+1)*num_ims
            # rotation images of original image:
            res[first_i:second_i, ...] = np.rot90(self.im, k, [-2, -1])
            # rotation images of flipped image:
            res[second_i:second_i + num_ims, ...] = np.rot90(flip_im, k,
                                                             [-2, -1])
        self.im = res

    def random_batch_for_real(self, batch_size, dim_chosen):
        return self.random_batch2d(batch_size, dim_chosen)

    def random_batch_for_fake(self, batch_size, dim_chosen):
        if self.dims == 3:
            return self.random_batch3d(batch_size, dim_chosen)
        else:  # dims = 2
            return self.random_batch2d(batch_size, dim_chosen)

    def random_batch3d(self, batch_size, dim_chosen):
        """
        :return: A batch of high resolution images,
        along the dimension chosen (0->x,1->y,2->z) in the 3d tif image.
        """
        res = np.zeros((batch_size, len(self.phases),
                        *self.high_l * np.ones(self.dims, dtype=int)),
                          dtype=self.im.dtype)
        for i in range(batch_size):
            res[i, ...] = self.generate_a_random_image3d(dim_chosen)
        # return a torch tensor:
        if self.down_sample:
            return self.down_sample_im(res)
        return torch.FloatTensor(res).to(device=self.device)

    def generate_a_random_image3d(self, dim_chosen):
        """
        :param dim_chosen: the dimension chosen for the slice
        :return: A random image of size res from the dimension chosen of the
        image. TODO I don't think we can separate between 2d and 3d here
        TODO because of slice
        """
        h_r = self.high_l
        # starting voxels
        s_ind = np.random.randint(np.array(self.im.shape[1:]) - h_r)
        e_ind = s_ind + h_r  # the end indices
        res_image = self.im[:, s_ind[0]:e_ind[0], s_ind[1]:e_ind[1],
                                s_ind[2]:e_ind[2]]
        # for different view, change the cube around..
        return res_image.transpose(0, *perms[dim_chosen])

    def random_batch2d(self, batch_size, dim_chosen):
        """
        :return: A batch of high resolution images, TODO 2d function
        along the dimension chosen (0->x,1->y,2->z) in the 3d tif image.
        """
        res = np.zeros((batch_size, len(self.phases), self.high_l,
                          self.high_l), dtype=self.im.dtype)
        for i in range(batch_size):
            res[i, :, :, :] = self.generate_a_random_image2d(dim_chosen)
        # return a torch tensor:
        if self.down_sample:
            return self.down_sample_im(res)
        return torch.FloatTensor(res).to(device=self.device)

    def generate_a_random_image2d(self, dim_chosen):
        """
        :param dim_chosen: the dimension chosen for the slice TODO 2d function
        :return: A random image of size res from the dimension chosen of the
        image.
        """
        # TODO sampling from an already low-res image
        # the starting pixels of the other dimensions:
        if self.stack:
            s_ind = np.random.randint(np.array(self.im.shape[2:]) -
                                      self.high_l)
            e_ind = s_ind + self.high_l
            slice_chosen = np.random.randint(self.im.shape[1])
            return self.im[:, slice_chosen, s_ind[0]:e_ind[0],
                                    s_ind[1]:e_ind[1]]
        s_ind = np.random.randint(np.array(self.im.shape[1:]) -
                                  self.high_l)
        e_ind = s_ind + self.high_l  # TODO warning somehow when it is going
        # TODO to be an error
        slice_chosen = np.random.randint(np.array(self.im.shape[1:]))
        if self.dim_im == 2:  # the image is just 2D
            return self.im[:, s_ind[0]:e_ind[0], s_ind[0]:e_ind[0]]
        if dim_chosen == 0:
            res_image = self.im[:, slice_chosen[0], s_ind[1]:e_ind[1],
                                    s_ind[2]:e_ind[2]]
        elif dim_chosen == 1:  # TODO: s_ind now returns error for this!
            res_image = self.im[:, s_ind[0]:e_ind[0], slice_chosen[1],
                                    s_ind[2]:e_ind[2]]
        else:  # dim_chosen == 2
            res_image = self.im[:, s_ind[0]:e_ind[0], s_ind[1]:e_ind[1],
                                    slice_chosen[2]]
        return res_image

    def all_image_batch(self):
        """
        :return: the 3d image ready to be fed into the G with dimensions
        1xCxDxHxW or 1xCxHxW
        """
        return self.im.unsqueeze(0)


def main():
    BM = BatchMaker('cpu')
    cubes = BM.random_batch3d(8, 0)
    print(BM.im.shape)
    print(cubes.size())


if __name__ == '__main__':
    main()
