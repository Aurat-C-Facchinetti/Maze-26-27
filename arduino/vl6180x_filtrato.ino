#include <Wire.h>
#include <Adafruit_VL6180X.h>

#define N_SAMPLES     5      // number of valid samples needed for each measurement cycle
#define MAX_ATTEMPTS  8      // maximum number of total attempts allowed to get N_SAMPLES valid measurements
#define FILTER        1      // type of filter used in the code, if it's 2 -> only considers values +-GATE_MM
#define GATE_MM       3      // decides how narrow is the range for a measure to be valid (only in FILTER = 2)
#define AVG_PERIOD    0x60   // integration time (how much time a sensor uses for a measure) -> higher = more precise measure, but longer time
#define ADDR          0x29

Adafruit_VL6180X tof;

// direct writing onto the sensors registers
void wr8(uint16_t reg, uint8_t v) {
  Wire.beginTransmission(ADDR);
  Wire.write(reg >> 8); 
  Wire.write(reg & 0xFF); 
  Wire.write(v);
  Wire.endTransmission();
}

// direct reading from the sensors registers
uint8_t rd8(uint16_t reg) {
  Wire.beginTransmission(ADDR);
  Wire.write(reg >> 8); 
  Wire.write(reg & 0xFF);
  Wire.endTransmission(false);
  Wire.requestFrom((uint8_t)ADDR, (uint8_t)1);
  return Wire.read();
}

// single measurement cycle. returns measurement status (0 = ok, 255 = timeout).
uint8_t readOnce(uint8_t &mm) {
  uint32_t t = micros();

  while (!(rd8(0x04D) & 0x01)) {
    if (micros() - t > 20000) return 255; // wait that the tof is ready, but with 20ms max startup time
  }

  wr8(0x018, 0x01); // single-shot measure start
  
  t = micros();

  while ((rd8(0x04F) & 0x07) != 0x04) {
    if (micros() - t > 20000) return 255; // waiting for a new measure (max 20ms)
  }
  
  mm = rd8(0x062);
  uint8_t st = rd8(0x04D) >> 4;

  wr8(0x015, 0x07); // clear interrupt value for next measure

  return st;
}

// sorts the N_SAMPLES values and returns the filtered result
float filtered(uint8_t buf[]) {
  uint8_t tmp[N_SAMPLES];

  // copy the current cycle's samples into a temporary array
  for (uint8_t i = 0; i < N_SAMPLES; i++) {
    tmp[i] = buf[i];
  }

  // Insertion Sort for ordering
  for (uint8_t i = 1; i < N_SAMPLES; i++) {
    uint8_t k = tmp[i];
    int8_t j = i - 1;

    while (j >= 0 && tmp[j] > k) {
      tmp[j + 1] = tmp[j];
      j--;
    }

    tmp[j + 1] = k;
  }

  // median extraction
  float med = tmp[N_SAMPLES / 2];

  if (FILTER == 1) {
    return med; // immediately returns the median value, outliers don't affect much the measure quality (unlike a simple average)
  }

  // if FILTER == 2: a value too distant from the median gets ignored
  float sum = 0;
  uint8_t c = 0;

  for (uint8_t i = 0; i < N_SAMPLES; i++) {
    if (abs((int)tmp[i] - (int)med) <= GATE_MM) {
      sum += tmp[i];
      c++;
    }
  }

  return (c == 0) ? med : (sum / c);
}

void setup() {
  Serial.begin(115200);
  while (!Serial) delay(1);

  Wire.begin();
  Wire.setClock(400000); // I2C frequency at 400kHz -> lower reading/writing time
  
  if (!tof.begin()) {
    Serial.println("VL6180X non trovato");
    while (1) delay(10);
  }

  wr8(0x10A, AVG_PERIOD);

  Serial.println("n;mm;status;tempo_us");
}

void loop() {
  static uint32_t n = 0;

  uint32_t t0 = micros();

  // buffer for the current measurement cycle only
  uint8_t buf[N_SAMPLES];

  uint8_t validSamples = 0;
  uint8_t attempts = 0;

  // try to collect N_SAMPLES valid measurements, invalid measurements are ignored and don't enter the buffer
  while (validSamples < N_SAMPLES && attempts < MAX_ATTEMPTS) {

    uint8_t mm;
    uint8_t st = readOnce(mm);

    attempts++;

    if (st == 0) {
      buf[validSamples] = mm;
      validSamples++;
    }
  }

  uint32_t dt = micros() - t0;

  // if enough valid measurements were collected, filter them
  if (validSamples == N_SAMPLES) {

    float out = filtered(buf);

    // send the filtered value
    Serial.print(n++);
    Serial.print(';');

    Serial.print(out);
    Serial.print(';');

    Serial.print(0);
    Serial.print(';');

    Serial.println(dt);
  }

  // if not enough valid measurements were obtained,
  // -1 means that this cycle did not produce a valid distance
  else {

    Serial.print(n++);
    Serial.print(';');

    Serial.print(-1);
    Serial.print(';');

    Serial.print(-1);
    Serial.print(';');

    Serial.println(dt);
  }
}
