import argparse
import cv2
import numpy as np
import sys
import os


def candidate():
    for w_r in range(11):
        for w_g in range(11):
            if w_r + w_g > 10:
                continue
            else:
                yield w_r/10, w_g/10, abs(round(1.0-w_r/10-w_g/10, 1))


def plot(image, file):
    return cv2.imwrite(file, image)


class Position:
    def __init__(self, w_r, w_g, w_b):
        self.w_r = w_r
        self.w_g = w_g
        self.w_b = w_b
        self.votes = 0

    def __eq__(self, other):
        if self.w_r == other.w_r and self.w_g == other.w_g and self.w_b == other.w_b:
            return True
        else:
            return False

    def __str__(self):
        return "({}, {}, {})".format(self.w_r, self.w_g, self.w_b)

    def __hash__(self):
        return int(10 * self.w_r + 1000 * self.w_g + 10000 * self.w_b)

    def __isneighbor__(self, other):
        if round(abs(self.w_r - other.w_r) + abs(self.w_g - other.w_g) + abs(self.w_b - other.w_b), 1) == 0.2:
            return True
        else:
            return False

    def vote(self):
        self.votes += 1


class JointBilateralFilter:
    def __init__(self, args, image):
        self.args = args

        # image definition
        self.image = image / 255.0
        self.height = self.image.shape[0]
        self.width = self.image.shape[1]

        # filtering factors
        self.sigma_s = None
        self.sigma_r = None

        # initialize
        self.bilateral_image = None
        self.joint_bilateral_image = dict()

    def filtered_image_gen(self):
        # saved path
        filename = os.path.join(self.args.output,
                                "s{}r{}".format(self.sigma_s, self.sigma_r),
                                os.path.splitext(os.path.basename(self.args.input))[0])
        if not os.path.exists(filename):
            os.makedirs(filename)

        # bilateral image
        self.bilateral_image = self.__filter(guide=None)
        if self.args.plot:
            print("Plotting bilateral image.")
            plot(self.bilateral_image, os.path.join(filename, "origin_bilateral.png"))

        # candidates (joint bilateral image)
        for w_r, w_g, w_b in candidate():
            y = w_r * self.image[:, :, 2] + w_g * self.image[:, :, 1] + w_b * self.image[:, :, 0]
            y = y / 255.0
            filtered = self.__filter(guide=y)
            if self.args.plot:
                print("Plotting filtered image: w_r:{} w_g:{} w_b:{}".format(w_r, w_g, w_b), end='\r')
                sys.stdout.write('\033[K')
                plot(filtered, os.path.join(filename, "w_r_{}_w_g_{}_w_b_{}.png".format(w_r, w_g, w_b)))

            pos = Position(w_r, w_g, w_b)
            self.joint_bilateral_image[pos] = filtered
        print("Finish filtering {} images".format(len(self.joint_bilateral_image)))

    def __filter(self, guide=None):
        filtered = np.zeros(self.image.shape)
        radius = 3 * self.sigma_s

        for x in range(self.width):
            for y in range(self.height):
                # edges
                y_bottom = np.maximum(0, y - radius)
                y_top = np.minimum(self.height, y + radius + 1)
                x_left = np.maximum(0, x - radius)
                x_right = np.minimum(self.width, x + radius + 1)

                # h_space: size = (2r + 1) x (2r + 1) (window size)
                h_space = [[i**2 + j**2 for i in range(x_left-x, x_right-x)] for j in range(y_bottom-y, y_top-y)]
                h_space = np.exp(-np.array(h_space) / (2 * self.sigma_s ** 2))

                # for single-channel image
                if guide is not None:
                    center_value = guide[y][x]
                    h_range = np.exp(
                        -(guide[y_bottom:y_top, x_left:x_right] - center_value) ** 2 / (2 * (self.sigma_r ** 2)))
                else:
                    center_value = self.image[y][x]
                    power = (self.image[y_bottom:y_top, x_left:x_right, 0] - center_value[0]) ** 2
                    power += (self.image[y_bottom:y_top, x_left:x_right, 1] - center_value[1]) ** 2
                    power += (self.image[y_bottom:y_top, x_left:x_right, 2] - center_value[2]) ** 2
                    h_range = np.exp(-power / (2 * (self.sigma_r ** 2)))

                # add together
                im = self.image[y_bottom:y_top, x_left:x_right]
                multi = np.multiply(h_space, h_range)
                filtered[y_bottom:y_top, x_left:x_right, 0] += np.multiply(multi, im[:, :, 0]) / np.sum(multi)
                filtered[y_bottom:y_top, x_left:x_right, 1] += np.multiply(multi, im[:, :, 1]) / np.sum(multi)
                filtered[y_bottom:y_top, x_left:x_right, 2] += np.multiply(multi, im[:, :, 2]) / np.sum(multi)

        filtered = filtered * 255.0
        return filtered

    def __cost(self, image):
        return np.sum(abs(image - self.bilateral_image))

    def __is_local_min(self, pos):
        print("Selected position(weight):", pos, "Local Min: ", end="")
        for neigh in self.joint_bilateral_image:
            if pos == neigh:
                continue
            elif pos.__isneighbor__(neigh):
                if self.__cost(self.joint_bilateral_image[neigh]) < self.__cost(self.joint_bilateral_image[pos]):
                    print("False")
                    return False
        print("True")
        return True

    def vote(self):
        for pos in self.joint_bilateral_image:
            if self.__is_local_min(pos):
                pos.vote()

    def vote_result(self):
        print("===========Result=============")
        for pos in self.joint_bilateral_image:
            print(pos, pos.vote)


def main(args):
    image = cv2.imread(os.path.join(args.input))  # BGR image

    # t1 = cv2.imread("advanced/s1r0.05/0c/origin_bilateral.png")
    # t2 = cv2.imread("advanced/s3r0.2/0c/w_r_0.0_w_g_0.1_w_b_0.9.png")
    # t3 = cv2.imread("advanced/s3r0.1/0c/origin_bilateral.png")
    # t4 = cv2.imread("advanced/s1r0.05/0c/w_r_0.0_w_g_0.1_w_b_0.9.png")
    # print(np.mean(t2==t4))
    # Conventional (BGR->YUV)
    if args.mode == "c":
        y = 0.299 * image[:, :, 2] + 0.587 * image[:, :, 1] + 0.114 * image[:, :, 0]
        filename = os.path.splitext(os.path.basename(args.input))[0] + '_y.png'
        plot(np.expand_dims(y, axis=2), os.path.join(args.output, filename))

    # Advanced (BGR->YUV)
    elif args.mode == "a":
        """
        start = time.time()
        for w_r, w_g, w_b in candidate():
            y = w_r * image[:, :, 2] + w_g * image[:, :, 1] + w_b * image[:, :, 0]
            bilateral_filter = JointBilateralFilter(args, image, y, args.sigma_s, args.sigma_r)
            bilateral_filter.filter()
            print("Plotting filtered image: w_r:{} w_g:{} w_b:{}".format(w_r, w_g, w_b))
            image_candidate[(w_r, w_g, w_b)] = bilateral_filter.filtered
            image_vote[(w_r, w_g, w_b)] = 0
            plot(bilateral_filter.filtered,
                 os.path.join(args.output, "w_r_{}_w_g_{}_w_b_{}.png".format(w_r, w_g, w_b)))
                
        print("Finish plotting 66 images. Time elapsed:", time.time() - start)
        """
        bilateral_filter = JointBilateralFilter(args, image)
        for sigma_s in [1, 2, 3]:
            for sigma_r in [0.05, 0.1, 0.2]:
                print("Progress: sigma_s={}, sigma_r={}".format(sigma_s, sigma_r))
                bilateral_filter.sigma_s = sigma_s
                bilateral_filter.sigma_r = sigma_r
                bilateral_filter.filtered_image_gen()
                bilateral_filter.vote()
                print("===========================================================")
        bilateral_filter.vote_result()

    else:
        raise NotImplementedError("Please specify the mode \"a\" for advanced or \"c\" for conventional method.")


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("-i", "--input", default="testdata/0c.png",
                        help="rgb input image")
    parser.add_argument("-o", "--output", default="advanced",
                        help="output directory")
    parser.add_argument("-p", "--plot", default=False,
                        help="plot for every candidate while initializing")
    parser.add_argument("--mode", default="a",
                        help="c: conventional; a: advanced")
    main(parser.parse_args())
