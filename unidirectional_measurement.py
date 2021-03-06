import os
os.environ['TF_CPP_MIN_LOG_LEVEL'] = '2'

from tensorflow.keras.models import load_model
import sys
import glob
import cv2
import numpy as np
import pydicom
import scipy.cluster.hierarchy as hcluster
import csaps

# find and load the pretrained DL classifier
# the pretrained model should be placed in the same directory

dir_path = os.path.dirname(os.path.realpath(__file__))

try:
    model = load_model(dir_path+'/lesion_classifier_32.hdf5')
    model.compile(loss='binary_crossentropy', optimizer='rmsprop', metrics=['accuracy'])
except OSError:
    print('SavedModel file lesion_classifier_32.hdf5 does not exist - the pretrained model should be placed in the same directory')

def main():
    '''
    Main for the running of the pipeline.
    Set the dcm file path and point within the target lesion.
    '''
    dir_path = os.path.dirname(os.path.realpath(__file__))

    dcm_path = sys.argv[1] # the first command line argument should be path to dcm file
    center_x = sys.argv[2]  # X-coordinate (in pixels) of any point within the target lesion
    center_y = sys.argv[3]  # Y-coordinate (in pixels) of any point within the target lesion
    measured_length = measure_size_with_classifier(dcm_path, center_x, center_y)
    print(round(measured_length,4))
    return measured_length
    
def measure_size_with_classifier(dcm_path, center_x, center_y):
    '''
    For the given dcm file and arbitrary point within the target lesion:
    (1) The file is passed to 'convert_dcm_to_pixel_array' to generate images with 
        various magnifications
    (2) The images with various magnifications are passed to the pretrained classifier
    (3) The classification results are passed to 'analyze_classification_results'
        and then converted into a final measurement 
    '''
    xdata=[]
    ydata=[]

    for i in range(0,57): # this tool supports lesion size measurement between 1.5cm and 7cm
        xdata+=[1.4+i/10+j/50 for j in range(0,5)]
        ydata+=[round(model.predict(convert_dcm_to_pixel_array(dcm_path, 1.4+i/10+j/50, center_x, center_y).reshape(-1, 128, 128, 1))[0][0], 3) for j in range(0,5)]

    pattern = [(x, y) for x, y in zip(xdata, ydata) if round(y,1) not in [0,1]]
    final_measurement = analyze_classification_results(pattern)
    return final_measurement

def analyze_classification_results(pattern):
    '''
    For the given classification results generated by the pretrained model:
    (1) Analyze classification pattern to identify a point where the classification fails
    (2) Detect and filter out interference pattern induced by adjacent anatomic structures
    
    stdev:  The small standard devation of x in pattern is observed only if there is no 
            neighboring anatomic structure interfering with LOI; in this case, final 
            meausrement can be derived in a simple manner. The large stdev value implies
            the necessity of additional process to handle the neighboring anatomic
            structures. We found stdev=0.4 reasonable in deciding whether the additional
            process is necessary or not.
    thresh: This variable is used to segregate patterns induced by each anatomic structure
            within the Field of View (FoV). If the value is too large, the pattern analyzer 
            gets vulnerable to the anatomic structures adjacent to Lesion of Interest (LOI).
            If the value is too small, the pattern analyzer may be given with incomplete 
            LOI pattern resulting in inaccurate measurement.
    '''
    stdev = np.std(list(zip(*pattern))[0])
    thresh = 0.35
    c_max = 0
    m_max = 0
    measurement = 0

    if stdev<0.4:
        measurement = np.mean(list(zip(*pattern))[0])

    if stdev>=0.4:
        data = np.array(list(zip([float(i[0]) for i in pattern],
                         [float(i[1]) for i in pattern])))
        clusters = hcluster.fclusterdata(data, thresh, criterion='distance')

        for cluster in clusters:
            x, y = zip(*[list(i[0]) for i in zip(data, clusters) if i[1]==cluster])
            x, y = np.array(x), np.array(y)
            m, c = np.linalg.lstsq(np.vstack([x, np.ones(len(x))]).T, y, rcond=None)[0]

            if m>m_max and len(set(clusters))>1 and (y.max()-y.min())>0.3:
                c_max = c
                m_max = m

        if len(set(clusters))>1 and m_max==0:
            for cluster in clusters:
                x, y = zip(*[list(i[0]) for i in zip(data, clusters) if i[1]==cluster])
                x, y = np.array(x), np.array(y)
                m, c = np.linalg.lstsq(np.vstack([x, np.ones(len(x))]).T, y, rcond=None)[0]

                if m>m_max:
                    c_max = c
                    m_max = m
            try:
                measurement = (0.5-c_max)/m_max
            except ZeroDivisionError:
                print('Model Failed - Not Measurable')
                measurement = 99
                pass

        elif len(set(clusters))==1:
            sp = csaps.CubicSmoothingSpline(x, y, smooth=0.9999)
            xs = np.linspace(x.min(), x.max(), int((x.max()-x.min())*4.3))
            ys = sp(xs)
            measurement = spline_measurement(xs,ys)

        elif len(set(clusters))>1 and m_max!=0:
            measurement = (0.5-c_max)/m_max

        else:
            print('Model Failed - Not Measurable')
            measurement = 99
            pass

    return measurement

def spline_measurement(xs,ys):
    ''' 
    For the given spline vertices: 
    (1) find an edge with the max slope 
    (2) perform linear regression along the edge
    (3) predict point x where f(x)=0.5
    (4) return x
    '''
    return sorted([[(ys[i-1]-ys[i])/(xs[i-1]-xs[i]),
                    (0.5-ys[i-1])*(xs[i-1]-xs[i])/(ys[i-1]-ys[i])+xs[i-1]] 
                   for i in range(1,len(xs))], 
                  reverse=True, key=lambda x: x[0])[0][1]

def convert_dcm_to_pixel_array(dcm_path, lesion_length, center_x, center_y):
    '''
    For the given dicom file:
    (1) The target is assumed to have the given lesion length (lesion_length)
    (2) Calculate the given size in centimeters into size in pixels
    (3) Add enough air padding around the original 512x512-pixel frame. This is to prevent 
        errors that may happen during the resizing of peripheral lung lesions.
        Hounsfield units (HU) of -1024 is used for radiodensity of air at STP for the padding.
    (4) Resize the pixel frame so that the target lesion will have size of 32 pixels.
    (5) Crop target lesion into 128x128-pixel frame using the given center point.
        (The pretrained classifier takes 128x128 images containing a target lesion)
    
    dcm_path:      Path to dicom file
    lesion_length: This is 'hypothetical' lesion size. (i) If true lesion size is larger than
                   this value, the resized lesion will have length smaller than 32 pixels. 
                   (ii) If true lesion size is smaller than this value, the resized lesion 
                   will have length larger than 32 pixels. (iii) If true lesion size is equal
                   to this value, the resized lesion will have length of 32 pixels, which 
                   causes the pretrained classifier to fail. 
    center_x:      X-coordinate (in pixels) of an arbitrary point within the target lesion
    center_y:      Y-coordinate (in pixels) of an arbitrary point within the target lesion    
    '''
    ds = pydicom.read_file(dcm_path)
    magnification = 3.2*ds.PixelSpacing[0]/lesion_length
    dimension_size = int(1280*magnification)
    center_x_padded = int((float(center_x) + 384) * magnification)
    center_y_padded = int((float(center_y) + 384) * magnification)
    parray_padded = np.ones((1280,1280)) * (-1024)
    parray_padded[384:896,384:896] = ds.pixel_array
    parray_magnified = cv2.resize(parray_padded, dsize=(dimension_size,dimension_size), 
                                  interpolation=cv2.INTER_CUBIC)
    final_image = parray_magnified[(center_y_padded - 64):(center_y_padded + 64), 
                                   (center_x_padded - 64):(center_x_padded + 64)]
    try:
        test_resizing = final_image.reshape(-1, 128, 128, 1) # check if resized properly
    except:
        print('Image resizing error - check source dcm file')

    return final_image

if __name__ == "__main__":
    main()

