#ifndef CLASSIFIER_H
#define CLASSIFIER_H

/* Logic nhận diện cường độ đòn đánh Aikido (Version 60-samples)
 * Chuyển đổi từ Decision Tree (Colab) sang C++
 */
int classifySignal(float peak_max, float acc_std, float peak_relative) {
    if (acc_std <= 2048.57) {
        if (acc_std <= 1843.78) {
            return 0; // Normal
        } else {
            if (peak_relative <= 2.10) return 1; // Intense
            else return 0; // Normal
        }
    } else {
        if (peak_max <= 23797.71) {
            if (peak_max <= 15882.40) return 1; // Intense
            else return 0; // Normal
        } else {
            return 1; // Intense
        }
    }
}

#endif