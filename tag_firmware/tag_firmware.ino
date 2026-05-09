/*
 * ============================================================
 *  UWB TAG FIRMWARE  — v3 (rewritten from official Makerfabs examples)
 *  For: Makerfabs ESP32 UWB Pro with Display
 *
 *  This is the MOVING device to track. Flash ONLY to the Pro+Display board.
 *
 *  Uses DW1000Ranging library (high-level TWR, built into mf_DW1000).
 *  The tag polls each anchor automatically — the ranging library handles
 *  the TWR protocol internally. No manual timestamp management needed.
 *
 *  Pins verified from official Makerfabs GitHub README.
 * ============================================================
 */

#include <SPI.h>
#include <DW1000Ranging.h>
#include <WiFi.h>
#include <WiFiUdp.h>
#include <Wire.h>
#include <Adafruit_GFX.h>
#include <Adafruit_SSD1306.h>

// ─── CONFIGURE BEFORE FLASHING ────────────────────────────────────────────────
const char* WIFI_SSID = "deep_laptop";
const char* WIFI_PASS = "anshu.com";
const char* PC_IP     = "10.8.60.205";
const int   UDP_PORT  = 5005;
// ──────────────────────────────────────────────────────────────────────────────

// Verified SPI + DW1000 pins for Makerfabs ESP32 UWB Pro with Display
// Source: https://github.com/Makerfabs/Makerfabs-ESP32-UWB README
#define SPI_SCK   18
#define SPI_MISO  19
#define SPI_MOSI  23
#define PIN_SS    21   // UWB_SS — Pro with Display uses GPIO21
#define PIN_RST   27
#define PIN_IRQ   34

// OLED pins — Pro with Display uses GPIO4=SDA, GPIO5=SCL
#define OLED_SDA   4
#define OLED_SCL   5
#define OLED_W   128
#define OLED_H    64

// Tag's own address — must be char[], not const char* or #define
char TAG_ADDRESS[] = "7D:00";

// How many anchors to expect
#define NUM_ANCHORS 3

Adafruit_SSD1306 display(OLED_W, OLED_H, &Wire, -1);
WiFiUDP udp;

// Store distances indexed by anchor short address
struct AnchorData {
  uint16_t shortAddr;
  float    distance;
  bool     active;
};

AnchorData anchors[NUM_ANCHORS] = {
  {0x1783, 0.0, false},  // "83:17" Anchor 1
  {0x1784, 0.0, false},  // "84:17" Anchor 2
  {0x1785, 0.0, false},  // "85:17" Anchor 3
};

unsigned long lastSendTime = 0;
const unsigned long SEND_INTERVAL_MS = 200;  // send to PC every 200ms

// ─── Helpers ─────────────────────────────────────────────────────────────────

int findAnchorIndex(uint16_t addr) {
  for (int i = 0; i < NUM_ANCHORS; i++) {
    if (anchors[i].shortAddr == addr) return i;
  }
  return -1;
}

int anchorIdForAddr(uint16_t addr) {
  // Map short address back to anchor ID 1/2/3
  if (addr == 0x1783) return 1;
  if (addr == 0x1784) return 2;
  if (addr == 0x1785) return 3;
  return 0;
}

void updateDisplay() {
  display.clearDisplay();
  display.setTextSize(1);
  display.setTextColor(SSD1306_WHITE);
  display.setCursor(0, 0);
  display.println("=== UWB Tag ===");
  display.println();
  for (int i = 0; i < NUM_ANCHORS; i++) {
    int aid = anchorIdForAddr(anchors[i].shortAddr);
    if (anchors[i].active) {
      display.printf("A%d: %.2f m\n", aid, anchors[i].distance);
    } else {
      display.printf("A%d: ---\n", aid);
    }
  }
  display.println();
  display.printf("%s", WiFi.localIP().toString().c_str());
  display.display();
}

void sendToPC() {
  // Format: "TAG:<d1>,<d2>,<d3>\n"
  // Send 0.0 if an anchor hasn't been heard from yet
  float d[4] = {0, 0, 0, 0};
  for (int i = 0; i < NUM_ANCHORS; i++) {
    int aid = anchorIdForAddr(anchors[i].shortAddr);
    if (aid >= 1 && aid <= 3 && anchors[i].active) {
      d[aid] = anchors[i].distance;
    }
  }

  char msg[64];
  snprintf(msg, sizeof(msg), "TAG:%.3f,%.3f,%.3f\n", d[1], d[2], d[3]);
  udp.beginPacket(PC_IP, UDP_PORT);
  udp.print(msg);
  udp.endPacket();
  Serial.printf("-> PC: %s", msg);
}

// ─── DW1000Ranging callbacks ─────────────────────────────────────────────────

void newRange() {
  uint16_t addr = DW1000Ranging.getDistantDevice()->getShortAddress();
  float dist    = DW1000Ranging.getDistantDevice()->getRange();

  int idx = findAnchorIndex(addr);
  if (idx >= 0) {
    anchors[idx].distance = dist;
    anchors[idx].active   = true;
  }

  int aid = anchorIdForAddr(addr);
  Serial.printf("Anchor %d [%04X]: %.3f m\n", aid, addr, dist);
}

void newDevice(DW1000Device* device) {
  uint16_t addr = device->getShortAddress();
  int aid = anchorIdForAddr(addr);
  Serial.printf("New anchor %d [%04X] joined\n", aid, addr);

  int idx = findAnchorIndex(addr);
  if (idx >= 0) anchors[idx].active = true;
}

void inactiveDevice(DW1000Device* device) {
  uint16_t addr = device->getShortAddress();
  int aid = anchorIdForAddr(addr);
  Serial.printf("Anchor %d [%04X] inactive\n", aid, addr);

  int idx = findAnchorIndex(addr);
  if (idx >= 0) anchors[idx].active = false;
}

// ─── Setup ───────────────────────────────────────────────────────────────────

void setup() {
  Serial.begin(115200);
  delay(1000);
  Serial.println("\n=== UWB Tag (Pro with Display) ===");

  // OLED
  Wire.begin(OLED_SDA, OLED_SCL);
  if (!display.begin(SSD1306_SWITCHCAPVCC, 0x3C)) {
    Serial.println("OLED init failed — check SDA/SCL pins");
  }
  display.clearDisplay();
  display.setTextSize(1);
  display.setTextColor(SSD1306_WHITE);
  display.setCursor(0, 0);
  display.println("UWB Tag Starting...");
  display.display();

  // WiFi
  WiFi.begin(WIFI_SSID, WIFI_PASS);
  Serial.print("Connecting to WiFi");
  while (WiFi.status() != WL_CONNECTED) {
    delay(500);
    Serial.print(".");
  }
  Serial.printf("\nWiFi: %s\n", WiFi.localIP().toString().c_str());
  udp.begin(UDP_PORT + 1);

  // Must init SPI with explicit pins BEFORE calling DW1000Ranging.initCommunication
  SPI.begin(SPI_SCK, SPI_MISO, SPI_MOSI, PIN_SS);

  // Init DW1000Ranging
  DW1000Ranging.initCommunication(PIN_RST, PIN_SS, PIN_IRQ);
  DW1000Ranging.attachNewRange(newRange);
  DW1000Ranging.attachNewDevice(newDevice);
  DW1000Ranging.attachInactiveDevice(inactiveDevice);

  // Start as tag — library automatically handles polling all nearby anchors
  DW1000Ranging.startAsTag(TAG_ADDRESS, DW1000.MODE_LONGDATA_RANGE_LOWPOWER, false);

  Serial.println("Tag ready — ranging started");
  updateDisplay();
}

// ─── Loop ────────────────────────────────────────────────────────────────────

void loop() {
  DW1000Ranging.loop();

  // Send distances to PC and update display periodically
  if (millis() - lastSendTime > SEND_INTERVAL_MS) {
    lastSendTime = millis();
    sendToPC();
    updateDisplay();
  }
}
