#pragma once
// =====================================================================
// TELEMETRY (Option 4) — WiFi station mode + HTTP POST to a Jetson-hosted
// AP/server. This is a CONVENIENCE LAYER ONLY, never a data source of
// truth — flash logging (see main.cpp's sessionFile) remains the
// guaranteed record regardless of whether any of this works.
//
// Why this exists: checking sensor health and retrieving data both used
// to require a fragile USB/Serial dance (open Serial Monitor, Ctrl+C,
// unplug, switch to battery, reset — see [[project-option4-jetson-plan]]).
// Pushing live telemetry over WiFi instead lets you watch status without
// ever touching USB during a real recording session.
//
// Bounded by design: every HTTP call here has a hard timeout and its
// result is ignored by the caller. An unbounded HTTP call inside a task
// would reproduce the exact USB-CDC blocking bug from 2026-07-08 (a task
// silently frozen waiting on I/O that may never complete) — just over
// WiFi instead of Serial. Never remove the timeouts below.
// =====================================================================

#include <WiFi.h>
#include <HTTPClient.h>

// Must match the Jetson's hotspot SSID/password (see jetson_server/setup_ap.md)
#define JETSON_SSID     "JetsonWearableAP"
#define JETSON_PASS     "wearable123"
// Default gateway IP for a NetworkManager-created hotspot — verify with
// `nmcli con show JetsonWearableAP` on the Jetson if this doesn't work.
#define JETSON_HOST     "10.42.0.1"
#define JETSON_PORT     8000

#define HTTP_TIMEOUT_MS 300   // hard cap on any single HTTP call — never remove

// Call once from setup(). WiFi.begin() is asynchronous — this does not
// block waiting for a connection, so it's safe to call even if the
// Jetson isn't reachable yet or ever.
static inline void telemetryBeginWiFi() {
    WiFi.mode(WIFI_STA);
    WiFi.begin(JETSON_SSID, JETSON_PASS);
}

// Best-effort JSON POST to the Jetson's /telemetry endpoint. Always
// returns within HTTP_TIMEOUT_MS. Silently does nothing if WiFi isn't
// currently connected — this avoids even attempting a slow connect()
// call, which is the single biggest risk of this whole layer. Caller
// must have already completed the flash write before calling this.
static inline void telemetryPush(const char* jsonPayload) {
    if (WiFi.status() != WL_CONNECTED) return;

    HTTPClient http;
    http.setConnectTimeout(HTTP_TIMEOUT_MS);
    http.setTimeout(HTTP_TIMEOUT_MS);

    char url[64];
    snprintf(url, sizeof(url), "http://%s:%d/telemetry", JETSON_HOST, JETSON_PORT);

    if (http.begin(url)) {
        http.addHeader("Content-Type", "application/json");
        http.POST((uint8_t*)jsonPayload, strlen(jsonPayload));  // return value intentionally ignored
        http.end();
    }
}
