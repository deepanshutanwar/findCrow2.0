/*
 * ============================================================
 *  UWB ANCHOR FIRMWARE  — v3 (rewritten from official Makerfabs examples)
 *  For: Makerfabs ESP32 UWB High Power (120m)
 *
 *  Flash this to all 3 anchor boards.
 *  Change ANCHOR_ID (1, 2, or 3) before flashing each board.
 *
 *  Uses DW1000Ranging library (high-level TWR, built into mf_DW1000).
 *  Pins verified from official Makerfabs GitHub README.
 * ============================================================
 */

#include <SPI.h>
#include <DW1000Ranging.h>
#include <WiFi.h>
#include <WiFiUdp.h>

// ─── CHANGE THESE BEFORE FLASHING ─────────────────────────────────────────────
#define ANCHOR_ID     3          // 1, 2, or 3 — must be unique per board

const char* WIFI_SSID = "deep_laptop";
const char* WIFI_PASS = "anshu.com";
const char* PC_IP     = "10.8.60.205";
const int   UDP_PORT  = 5005;
// ──────────────────────────────────────────────────────────────────────────────

// Verified SPI + DW1000 pins for Makerfabs ESP32 UWB High Power board
// Source: https://github.com/Makerfabs/Makerfabs-ESP32-UWB README
#define SPI_SCK   18
#define SPI_MISO  19
#define SPI_MOSI  23
#define PIN_SS     4   // DW_CS — High Power board uses GPIO4 (NOT 21)
#define PIN_RST   27
#define PIN_IRQ   34

// Unique short address per anchor (must be char[], not const char*)
char ANCHOR_ADDR_0[] = "";
char ANCHOR_ADDR_1[] = "83:17";
char ANCHOR_ADDR_2[] = "84:17";
char ANCHOR_ADDR_3[] = "85:17";
char* ANCHOR_ADDRESSES[] = { ANCHOR_ADDR_0, ANCHOR_ADDR_1, ANCHOR_ADDR_2, ANCHOR_ADDR_3 };

WiFiUDP udp;

// ─── DW1000Ranging callbacks ─────────────────────────────────────────────────

void newRange() {
  float dist = DW1000Ranging.getDistantDevice()->getRange();
  uint16_t shortAddr = DW1000Ranging.getDistantDevice()->getShortAddress();

  Serial.printf("Anchor %d -> Tag [%04X]: %.3f m\n", ANCHOR_ID, shortAddr, dist);

  // Send to PC: "A<id>:<distance>\n"
  char msg[32];
  snprintf(msg, sizeof(msg), "A%d:%.3f\n", ANCHOR_ID, dist);
  udp.beginPacket(PC_IP, UDP_PORT);
  udp.print(msg);
  udp.endPacket();
}

void newDevice(DW1000Device* device) {
  Serial.printf("Anchor %d: Tag joined: %04X\n", ANCHOR_ID, device->getShortAddress());
}

void inactiveDevice(DW1000Device* device) {
  Serial.printf("Anchor %d: Tag lost: %04X\n", ANCHOR_ID, device->getShortAddress());
}

// ─── Setup ───────────────────────────────────────────────────────────────────

void setup() {
  Serial.begin(115200);
  delay(1000);
  Serial.printf("\n=== UWB Anchor %d ===\n", ANCHOR_ID);

  // WiFi
  WiFi.begin(WIFI_SSID, WIFI_PASS);
  Serial.print("Connecting to WiFi");
  while (WiFi.status() != WL_CONNECTED) {
    delay(500);
    Serial.print(".");
  }
  Serial.printf("\nWiFi: %s\n", WiFi.localIP().toString().c_str());
  udp.begin(UDP_PORT);

  // Must init SPI with explicit pins BEFORE calling DW1000Ranging.initCommunication
  SPI.begin(SPI_SCK, SPI_MISO, SPI_MOSI, PIN_SS);

  // Init DW1000Ranging
  DW1000Ranging.initCommunication(PIN_RST, PIN_SS, PIN_IRQ);
  DW1000Ranging.attachNewRange(newRange);
  DW1000Ranging.attachNewDevice(newDevice);
  DW1000Ranging.attachInactiveDevice(inactiveDevice);

  // Start as anchor
  DW1000Ranging.startAsAnchor(
    ANCHOR_ADDRESSES[ANCHOR_ID],
    DW1000.MODE_LONGDATA_RANGE_LOWPOWER,
    false  // false = use static address, not random
  );

  Serial.printf("Anchor %d ready (%s) — waiting for tag...\n",
                ANCHOR_ID, ANCHOR_ADDRESSES[ANCHOR_ID]);
}

// ─── Loop ────────────────────────────────────────────────────────────────────

void loop() {
  DW1000Ranging.loop();
}
