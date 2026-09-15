#pragma once
// =====================================================================
// TELEMETRY (Option 4) — UDP transport.
//
// Chosen over HTTP (see http_client.h, kept intact and unused — not
// deleted, in case we want to switch back or compare) because UDP has
// no connection state to lose and no connect() step to hang on. That
// structurally avoids two of the three biggest pains named for this
// layer: "connection lost mid-session" and "can't connect at all."
// See [[project-option4-jetson-plan]] for the full reasoning and the
// known bug list for this transport.
//
// WiFi station-mode connection (telemetryBeginWiFi()) is shared with
// http_client.h — it's transport-agnostic, no need to duplicate it here.
//
// IMPORTANT — this sends UNICAST to JETSON_UDP_HOST, not a broadcast
// address. The earlier disabled self-hosted-AP code used a broadcast
// address ("192.168.4.255") that only made sense on that AP's own
// subnet. Reusing a broadcast address here would silently send packets
// nowhere on the Jetson's subnet — exactly the "most painful UDP bug"
// already identified. Don't reintroduce it.
// =====================================================================

#include <WiFi.h>
#include <WiFiUdp.h>

#define JETSON_UDP_HOST "10.42.0.1"   // must match http_client.h's JETSON_HOST
#define JETSON_UDP_PORT 8001          // separate port from the (disabled) HTTP server

static WiFiUDP telemetryUdp;
static bool    telemetryUdpBegun = false;

// Best-effort JSON send. Never blocks: beginPacket/write/endPacket don't
// wait for any response — no handshake, no acknowledgment, that's the
// whole point of choosing UDP. We still explicitly skip sending when
// WiFi isn't connected, rather than let an uninitialized/disconnected
// socket do something undefined.
static inline void telemetrySendUDP(const char* jsonPayload) {
    if (WiFi.status() != WL_CONNECTED) return;

    if (!telemetryUdpBegun) {
        telemetryUdp.begin(0);   // ephemeral local port — we only ever send, never listen
        telemetryUdpBegun = true;
    }

    telemetryUdp.beginPacket(JETSON_UDP_HOST, JETSON_UDP_PORT);
    telemetryUdp.write((const uint8_t*)jsonPayload, strlen(jsonPayload));
    telemetryUdp.endPacket();   // return value intentionally ignored — best-effort
}
