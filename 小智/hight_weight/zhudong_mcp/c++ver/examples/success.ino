#define RXD2 16
#define TXD2 17

unsigned long lastReceiveTime = 0;
unsigned long receiveCount = 0;
unsigned long sendCount = 0;

uint8_t rxBuffer[256];
int rxIndex = 0;

void setup() {
  Serial.begin(115200);
  Serial2.begin(115200, SERIAL_8N1, RXD2, TXD2);
  
  Serial.println("\n========================================");
  Serial.println("606 Body Measurement Tool v1.0");
  Serial.println("========================================");
  Serial.println("Quick Commands:");
  Serial.println("  1 - Read Version (0x54)");
  Serial.println("  2 - Get Temperature & Humidity (0x41)");
  Serial.println("  3 - Height Measurement (0x42)");
  Serial.println("  4 - Weight Measurement (0x43)");
  Serial.println("  5 - Height & Weight Measurement (0x47)");
  Serial.println("  6 - Vision Test (0x45)");
  Serial.println("  h - Show Help");
  Serial.println("  s - Show Statistics");
  Serial.println("========================================\n");
}

void loop() {
  if (Serial2.available()) {
    while (Serial2.available()) {
      uint8_t inByte = Serial2.read();
      
      if (inByte == 0x5F || inByte == 0x5E) {
        rxIndex = 0;
        rxBuffer[rxIndex++] = inByte;
      } 
      else if (rxIndex > 0 && rxIndex < 256) {
        rxBuffer[rxIndex++] = inByte;
        
        if (inByte == 0x0D && rxIndex >= 4) {
          receiveCount++;
          lastReceiveTime = millis();
          parseAndDisplay(rxBuffer, rxIndex);
          rxIndex = 0;
        }
      }
      delay(2);
    }
  }
  
  if (Serial.available()) {
    char cmd = Serial.read();
    handleCommand(cmd);
  }
}

void parseAndDisplay(uint8_t* data, int len) {
  Serial.print("\n[");
  Serial.print(millis() / 1000.0, 3);
  Serial.print("s] RX #");
  Serial.print(receiveCount);
  Serial.println(":");
  
  // Raw HEX data
  Serial.print("  RAW: ");
  for (int i = 0; i < len; i++) {
    if (data[i] < 0x10) Serial.print("0");
    Serial.print(data[i], HEX);
    Serial.print(" ");
  }
  Serial.println();
  
  if (len < 4) {
    Serial.println("  [!] Data too short");
    return;
  }
  
  uint8_t header = data[0];
  uint8_t length = data[1];
  uint8_t cmd = data[2];
  uint8_t tail = data[len - 1];
  
  if (header != 0x5F && header != 0x5E) {
    Serial.println("  [!] Invalid header");
    return;
  }
  
  if (tail != 0x0D) {
    Serial.println("  [!] Invalid tail");
    return;
  }
  
  Serial.print("  Type: ");
  Serial.println(header == 0x5F ? "Response" : "Command");
  Serial.print("  CMD: 0x");
  Serial.println(cmd, HEX);
  
  switch(cmd) {
    case 0x54: // Version
      if (len >= 5) {
        Serial.print("  >> Version: V");
        Serial.print(data[3]);
        Serial.print(".");
        Serial.println(data[4]);
      }
      break;
      
    case 0x41: // Temperature & Humidity
      if (len >= 7) {
        float temp = ((data[3] << 8) | data[4]) / 10.0;
        float humi = ((data[5] << 8) | data[6]) / 10.0;
        Serial.print("  >> Temperature: ");
        Serial.print(temp);
        Serial.println(" C");
        Serial.print("  >> Humidity: ");
        Serial.print(humi);
        Serial.println(" %");
      }
      break;
      
    case 0x42: // Height
      if (len >= 6) {
        float height = ((data[3] << 8) | data[4]) / 10.0;
        uint8_t status = data[5];
        Serial.print("  >> Height: ");
        Serial.print(height);
        Serial.print(" cm [");
        printStatus(status);
        Serial.println("]");
      }
      break;
      
    case 0x43: // Weight
      if (len >= 6) {
        float weight = ((data[3] << 8) | data[4]) / 10.0;
        uint8_t status = data[5];
        Serial.print("  >> Weight: ");
        Serial.print(weight);
        Serial.print(" kg [");
        printStatus(status);
        Serial.println("]");
      }
      break;
      
    case 0x47: // Height & Weight
      if (len >= 9) {
        float height = ((data[3] << 8) | data[4]) / 100.0;
        uint8_t heightStatus = data[5];
        float weight = ((data[6] << 8) | data[7]) / 100.0;
        uint8_t weightStatus = data[8];
        
        Serial.print("  >> Height: ");
        Serial.print(height);
        Serial.print(" cm [");
        printStatus(heightStatus);
        Serial.println("]");
        
        Serial.print("  >> Weight: ");
        Serial.print(weight);
        Serial.print(" kg [");
        printStatus(weightStatus);
        Serial.println("]");
        
        // Calculate BMI
        if (height > 0 && weight > 0) {
          float bmi = weight / ((height / 100) * (height / 100));
          Serial.print("  >> BMI: ");
          Serial.print(bmi, 2);
          Serial.print(" (");
          if (bmi < 18.5) Serial.print("Underweight");
          else if (bmi < 24) Serial.print("Normal");
          else if (bmi < 28) Serial.print("Overweight");
          else Serial.print("Obese");
          Serial.println(")");
        }
      }
      break;
      
    case 0x45: // Vision
      if (len >= 7) {
        float leftEye = ((data[3] << 8) | data[4]) / 10.0;
        float rightEye = ((data[5] << 8) | data[6]) / 10.0;
        Serial.print("  >> Left Eye: ");
        Serial.println(leftEye);
        Serial.print("  >> Right Eye: ");
        Serial.println(rightEye);
      }
      break;
      
    case 0x4F: // Volume
      if (len >= 4) {
        Serial.print("  >> Volume: ");
        Serial.print(data[3]);
        Serial.println(" (0-5)");
      }
      break;
      
    case 0x50: // Brightness
      if (len >= 4) {
        Serial.print("  >> Brightness: ");
        Serial.print(data[3]);
        Serial.println(" (0-5)");
      }
      break;
      
    case 0x5A: // Infrared
      if (len >= 7) {
        Serial.print("  >> IR Signal: Addr=0x");
        Serial.print(data[3], HEX);
        Serial.print(" AddrInv=0x");
        Serial.print(data[4], HEX);
        Serial.print(" Cmd=0x");
        Serial.print(data[5], HEX);
        Serial.print(" CmdInv=0x");
        Serial.println(data[6], HEX);
      }
      break;
      
    default:
      Serial.println("  [!] Unknown command");
  }
  
  Serial.println();
}

void printStatus(uint8_t status) {
  switch(status) {
    case 0x00:
      Serial.print("Measuring");
      break;
    case 0x01:
      Serial.print("Complete");
      break;
    case 0x02:
      Serial.print("Failed");
      break;
    default:
      Serial.print("Unknown");
  }
}

void sendCommand(uint8_t cmd, uint8_t* data = NULL, int dataLen = 0) {
  uint8_t buffer[256];
  int index = 0;
  
  buffer[index++] = 0x5E;
  buffer[index++] = 1 + dataLen;
  buffer[index++] = cmd;
  
  for (int i = 0; i < dataLen; i++) {
    buffer[index++] = data[i];
  }
  
  buffer[index++] = 0x0D;
  
  Serial2.write(buffer, index);
  sendCount++;
  
  Serial.print("\n[TX] CMD 0x");
  Serial.print(cmd, HEX);
  Serial.print(": ");
  for (int i = 0; i < index; i++) {
    if (buffer[i] < 0x10) Serial.print("0");
    Serial.print(buffer[i], HEX);
    Serial.print(" ");
  }
  Serial.println("\n");
}

void handleCommand(char cmd) {
  switch(cmd) {
    case '1':
      Serial.println("-> Read Version");
      sendCommand(0x54);
      break;
      
    case '2':
      Serial.println("-> Get Temperature & Humidity");
      sendCommand(0x41);
      break;
      
    case '3':
      Serial.println("-> Start Height Measurement");
      sendCommand(0x42);
      break;
      
    case '4':
      Serial.println("-> Start Weight Measurement");
      sendCommand(0x43);
      break;
      
    case '5':
      Serial.println("-> Start Height & Weight Measurement");
      sendCommand(0x47);
      break;
      
    case '6':
      Serial.println("-> Start Vision Test");
      sendCommand(0x45);
      break;
      
    case 'h':
    case 'H':
      printHelp();
      break;
      
    case 's':
    case 'S':
      printStats();
      break;
      
    case 'c':
    case 'C':
      receiveCount = 0;
      sendCount = 0;
      Serial.println("[OK] Statistics cleared\n");
      break;
      
    case '\n':
    case '\r':
      break;
      
    default:
      Serial.println("[!] Unknown command, press 'h' for help\n");
  }
}

void printHelp() {
  Serial.println("\n========================================");
  Serial.println("Command List:");
  Serial.println("  1 - Read Version (0x54)");
  Serial.println("  2 - Get Temperature & Humidity (0x41)");
  Serial.println("  3 - Height Measurement (0x42)");
  Serial.println("  4 - Weight Measurement (0x43)");
  Serial.println("  5 - Height & Weight Measurement (0x47)");
  Serial.println("  6 - Vision Test (0x45)");
  Serial.println("  h - Show Help");
  Serial.println("  s - Show Statistics");
  Serial.println("  c - Clear Statistics");
  Serial.println("========================================\n");
}

void printStats() {
  Serial.println("\n========================================");
  Serial.println("Statistics:");
  Serial.print("  RX Count: ");
  Serial.println(receiveCount);
  Serial.print("  TX Count: ");
  Serial.println(sendCount);
  Serial.print("  Uptime: ");
  Serial.print(millis() / 1000.0, 1);
  Serial.println(" sec");
  if (lastReceiveTime > 0) {
    Serial.print("  Last RX: ");
    Serial.print((millis() - lastReceiveTime) / 1000.0, 1);
    Serial.println(" sec ago");
  }
  Serial.println("========================================\n");
}