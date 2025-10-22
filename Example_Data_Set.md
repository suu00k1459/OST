## Intel Lab Data Dataset

**Source:** MIT Computer Science and Artificial Intelligence Laboratory (CSAIL)

**URL:** http://db.csail.mit.edu/labdata/data.txt

**Dataset Description:**
The Intel Berkeley Research Lab deployed 54 sensor nodes (Mica2Dot sensors) throughout their laboratory facility. These sensors collected timestamped data including temperature, humidity, light, and voltage readings.

**Dataset Specifications:**
- **Records:** 152,542 sensor readings
- **Duration:** Approximately 1 hour 20 minutes of data
- **Date:** February 28, 2004
- **Time Range:** 00:00:02 to 01:19:54
- **Number of Sensors:** 54 devices (device_001 to device_054)
- **File Size:** 5.47 MB (raw text format)

**Data Format:**
```
epoch device_id temperature humidity light voltage
```

**Sensor Measurements:**
1. **Temperature:** Celsius (range: 14.01°C to 27.96°C)
2. **Humidity:** Percentage (range: 25.16% to 52.49%)
3. **Light:** Lux (range: 0 to 1847.36)
4. **Voltage:** Volts (range: 2.41V to 3.16V)

**Data Quality:**
- 152,542 total records
- 5 duplicate records removed
- 4 outliers removed
- 152,533 valid records after cleaning

**Use Case:**
This dataset is widely used for evaluating distributed sensing systems, data stream processing, and machine learning algorithms in IoT environments. It provides real-world sensor data with natural variations and patterns suitable for anomaly detection and federated learning research.

**Citation:**
Intel Berkeley Research Lab, "Data from 54 sensors deployed in the Intel Berkeley Research Lab," MIT CSAIL, 2004.