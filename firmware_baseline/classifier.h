#ifndef CLASSIFIER_H
#define CLASSIFIER_H

int classifySignal(float peak_max, float acc_std, float peak_relative) {
    if (acc_std <= 2488.65) {
        if (acc_std <= 1827.03) {
            if (peak_relative <= 2.13) {
                return 0; // Class 0
            } else {
                return 0; // Class 0
            }
        } else {
            if (peak_relative <= 2.11) {
                return 1; // Class 1
            } else {
                return 0; // Class 0
            }
        }
    } else {
        if (acc_std <= 3785.27) {
            if (peak_max <= 17406.41) {
                return 1; // Class 1
            } else {
                return 0; // Class 0
            }
        } else {
            if (acc_std <= 3986.92) {
                return 1; // Class 1
            } else {
                return 1; // Class 1
            }
        }
    }
}

#endif
