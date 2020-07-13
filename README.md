# Introduction

This repository contains codes for semi-automated unidirectional measurement of lung lesions in compliance with Response Evaluation Criteria in Solid 1.1 (RECIST 1.1). 

The proposed algorithm is designed to offer a binary answer (yes or no) for the following question: 

*In the given image, is its lesion size smaller or larger than [___] cm?

In the blank, we start from 1.49cm, which is the minimum measurable lesion size suggested by RECIST 1.1 guideline, up to 7.0cm with an increment of 0.01cm. 
**Disclaimer: The algorithm may not work reliably for lesions larger than 6cm due to the lack of training data.

Once the algorithm fails to answer the question, we assumed the failure occurred because the lesion size approximates to the given length. For example, if the algorithm failed to answer whether the lesion size is smaller or larger than 3.568cm, then we assumed the failure may have occurred as the true lesion size approximates to 3.568cm. Thus, the final measurement would be 3.568cm.

Sample images are included in sample_images/ directory for testing purposes. You can find their corresponding measurements in sample_images.csv file. 

# Sample Usage
* First download and locate files and directory
* find the measurement. In this example, 28170.dcm file was selected. According to sample_images.csv file, its measurement center is (219.6057465, 298.1731035). The algorithm works for any arbitrary point inside the lesion, so we will simply use (219, 298) as its input.
* do that
'''
path/to/sample_images/28170.dcm
'''
* you should see the following result
'''
2.71
'''

## License

GNU General Public License v3.0+ (see LICENSE file or https://www.gnu.org/licenses/gpl-3.0.txt for full text)

Copyright 2020, Clemson University - Department of Public Health Sciences



python3 /path/to/unidirectional_measurement.py /path/to/sample_images/28170.dcm 219 298