// Minimal buzzer isolation test — no FreeRTOS, no mutex, no sensors.
// Cycles through 4 phases forever, printing which one is active so you
// can match what you hear (or don't) to a specific mechanism.
#include <Arduino.h>

#define BUZZER_PIN 3   // D2 on XIAO ESP32-S3 — same pin as main firmware

void setup() {
    Serial.begin(115200);
    delay(2000);
    pinMode(BUZZER_PIN, OUTPUT);
    digitalWrite(BUZZER_PIN, LOW);
    Serial.println("[TEST] Buzzer isolation test starting.");
}

void loop() {
    Serial.println("[PHASE] digitalWrite HIGH (raw DC, 1s)");
    digitalWrite(BUZZER_PIN, HIGH);
    delay(1000);
    digitalWrite(BUZZER_PIN, LOW);
    delay(500);

    Serial.println("[PHASE] tone() 800Hz — matches session-transition beep (1s)");
    tone(BUZZER_PIN, 800);
    delay(1000);
    noTone(BUZZER_PIN);
    delay(500);

    Serial.println("[PHASE] tone() 3000Hz — matches PPG-loss warning (1s)");
    tone(BUZZER_PIN, 3000);
    delay(1000);
    noTone(BUZZER_PIN);
    delay(500);

    Serial.println("[PHASE] silence (1s)");
    delay(1000);
}
