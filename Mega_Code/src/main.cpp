#include <Arduino.h>
#include <ModbusMaster.h>

#define CTRL_PIN 4  // Chân điều khiển DE/RE cho MAX485

ModbusMaster node;

uint16_t cells[16]; 
float totalVol = 0;
float current = 0;
uint8_t soc = 0;
uint8_t soh = 0; // Thêm biến lưu SOH

void preTransmission() {
  digitalWrite(CTRL_PIN, HIGH);
}

void postTransmission() {
  digitalWrite(CTRL_PIN, LOW);
}

void setup() {
  Serial.begin(115200);
  Serial2.begin(115200);
  
  pinMode(CTRL_PIN, OUTPUT);
  digitalWrite(CTRL_PIN, LOW);

  node.begin(15, Serial2);
  node.preTransmission(preTransmission);
  node.postTransmission(postTransmission);
  
  Serial.println("\n--- ARDUINO MEGA MODBUS RTU - JK BMS READY ---");
}

void loop() {
  bool readSuccess = true;

  // 1. Đọc 16 Cell
  if (node.readHoldingRegisters(0x1200, 16) == node.ku8MBSuccess) {
    for (int i = 0; i < 16; i++) {
      cells[i] = node.getResponseBuffer(i);
    }
  } else { readSuccess = false; }
  delay(30);

  // 2. Đọc Tổng Điện Áp
  if (node.readHoldingRegisters(0x1290, 2) == node.ku8MBSuccess) {
    uint32_t rawV = ((uint32_t)node.getResponseBuffer(0) << 16) | node.getResponseBuffer(1);
    totalVol = rawV / 1000.0;
  }
  delay(30);

  // 3. Đọc Dòng Điện (Đã vá lỗi bù dấu của JK BMS)
  if (node.readHoldingRegisters(0x1298, 2) == node.ku8MBSuccess) {
    uint32_t highWord = node.getResponseBuffer(0);
    uint32_t lowWord  = node.getResponseBuffer(1);
    uint32_t tempI = (highWord << 16) | lowWord;

    if (highWord == 0x0000 && lowWord >= 0x8000) {
      tempI = 0xFFFF0000 | lowWord;
    }
    
    int32_t rawI = (int32_t)tempI;
    current = rawI / 1000.0;
  }
  delay(30);

  // 4. Đọc SOC %
  if (node.readHoldingRegisters(0x12A6, 1) == node.ku8MBSuccess) {
    soc = node.getResponseBuffer(0) & 0xFF; 
  }
  delay(30);

  // 5. Đọc SOH % (Địa chỉ 0x12B8)
  // Theo tài liệu, thanh ghi này chứa SOH ở byte cao, Precharge ở byte thấp
  if (node.readHoldingRegisters(0x12B8, 1) == node.ku8MBSuccess) {
    soh = node.getResponseBuffer(0) >> 8; 
  }

  // --- IN DỮ LIỆU RA MÀN HÌNH ---
  if (readSuccess) {
    Serial.println("\n--- JK BMS TELEMETRY DATA ---");
    Serial.print("Total Voltage: "); Serial.print(totalVol, 2); Serial.print(" V  |  ");
    Serial.print("Current: "); Serial.print(current, 2); Serial.print(" A  |  ");
    Serial.print("SOC: "); Serial.print(soc); Serial.print(" %  |  ");
    Serial.print("SOH: "); Serial.print(soh); Serial.println(" %"); // In thêm SOH
    
    Serial.println("\n- 16 CELL VOLTAGES (V) -");
    for (int i = 0; i < 16; i++) {
      Serial.print("C"); 
      if (i < 9) Serial.print("0");
      Serial.print(i + 1);
      Serial.print(": ");
      Serial.print(cells[i] / 1000.0, 3);
      Serial.print("\t");
      if ((i + 1) % 4 == 0) Serial.println();
    }
    Serial.println("-------------------------------");
  } else {
    Serial.println("Loi Modbus: Mat ket noi hoac BMS tu choi tra loi!");
  }

  delay(2000); 
}