#include <WiFi.h>
#include <WebServer.h>
#include <FastLED.h>
#define FASTLED_ALLOW_INTERRUPTS 0

#define LED_PIN  5
#define NUM_LEDS 12
#define LED_TYPE WS2812B
#define COLOR_ORDER GRB

CRGB leds[NUM_LEDS];

// --- Wi-Fi Credentials ---
const char* ssid = //"wifi name";
const char* password = //"wifi password";

// Create a web server on port 80
WebServer server(80);

// Current state
String currentState = "idle";

// Animation variables
unsigned long lastAnimationUpdate = 0;
int animationPosition = 0;

void setup() {
  FastLED.addLeds<LED_TYPE, LED_PIN, COLOR_ORDER>(leds, NUM_LEDS);
  FastLED.setBrightness(50);
  Serial.begin(115200);
  
  // Connect to WiFi
  WiFi.begin(ssid, password);
  Serial.print("Connecting to WiFi");
  while (WiFi.status() != WL_CONNECTED) {
    delay(500);
    Serial.print(".");
  }
  Serial.println("\nConnected!");
  Serial.print("ESP32 IP Address: ");
  Serial.println(WiFi.localIP());
  
  // Define server routes
  server.on("/status", HTTP_POST, handleStatus);
  server.on("/health", HTTP_GET, handleHealth);
  
  // Start server
  server.begin();
  Serial.println("Web server started!");
  
  // Show idle state (red)
  setLEDState("idle");
}

void loop() {
  server.handleClient();  // Handle incoming HTTP requests
  
  // Animate thinking state
  if (currentState == "thinking") {
    unsigned long currentTime = millis();
    if (currentTime - lastAnimationUpdate >= 100) {  // Update every 100ms
      lastAnimationUpdate = currentTime;
      updateThinkingAnimation();
    }
  }
}

void handleStatus() {
  if (server.hasArg("plain")) {
    String body = server.arg("plain");
    
    // Debug output
    Serial.println("=== RECEIVED POST ===");
    Serial.println(body);
    Serial.println("====================");
    
    // More flexible matching - check if body contains the state word
    body.toLowerCase();  // Convert to lowercase for easier matching
    
    if (body.indexOf("listening") >= 0) {
      Serial.println("MATCHED: listening");
      setLEDState("listening");
      currentState = "listening";
    } 
    else if (body.indexOf("thinking") >= 0) {
      Serial.println("MATCHED: thinking");
      setLEDState("thinking");
      currentState = "thinking";
    }
    else if (body.indexOf("speaking") >= 0) {
      Serial.println("MATCHED: speaking");
      setLEDState("speaking");
      currentState = "speaking";
    }
    else if (body.indexOf("idle") >= 0) {
      Serial.println("MATCHED: idle");
      setLEDState("idle");
      currentState = "idle";
    }
    else {
      Serial.println("NO MATCH! Unknown state");
      Serial.print("Body length: ");
      Serial.println(body.length());
    }
    
    server.send(200, "application/json", "{\"status\":\"ok\"}");
  } else {
    Serial.println("ERROR: No body received");
    server.send(400, "application/json", "{\"error\":\"no body\"}");
  }
}

void handleHealth() {
  String response = "{\"status\":\"ok\",\"state\":\"" + currentState + "\"}";
  server.send(200, "application/json", response);
}

void setLEDState(String state) {
  Serial.println("Setting LED state: " + state);
  
  if (state == "listening") {
    // Blue - actively listening
    for(int i = 0; i < NUM_LEDS; i++) {
      leds[i] = CRGB::Blue;
    }
    FastLED.show();
  }
  else if (state == "thinking") {
    // Start thinking animation (will be updated in loop)
    currentState = "thinking";
  }
  else if (state == "speaking") {
    // Green - teddy is talking
    for(int i = 0; i < NUM_LEDS; i++) {
      leds[i] = CRGB::Green;
    }
    FastLED.show();
  }
  else if (state == "idle") {
    // Red - waiting/idle
    for(int i = 0; i < NUM_LEDS; i++) {
      leds[i] = CRGB::Red;
    }
    FastLED.show();
  }
  else {
    // Unknown state - purple
    for(int i = 0; i < NUM_LEDS; i++) {
      leds[i] = CRGB::Purple;
    }
    FastLED.show();
  }
}

void updateThinkingAnimation() {
  // Spinning single orange dot with trailing effect
  
  // Clear all LEDs
  for(int i = 0; i < NUM_LEDS; i++) {
    leds[i] = CRGB::Black;
  }
  
  // Light up the current position
  leds[animationPosition] = CRGB::Orange;
  
  // Add a trailing effect
  int trail1 = (animationPosition - 1 + NUM_LEDS) % NUM_LEDS;
  int trail2 = (animationPosition - 2 + NUM_LEDS) % NUM_LEDS;
  leds[trail1] = CRGB(128, 64, 0);  // Dimmer orange
  leds[trail2] = CRGB(64, 32, 0);   // Even dimmer
  
  FastLED.show();
  
  // Move to next position
  animationPosition = (animationPosition + 1) % NUM_LEDS;
}