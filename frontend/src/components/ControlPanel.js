import React, { useState, useEffect } from "react";
import "./ControlPanel.css";

function ControlPanel({
    onStartPreprocessing,
    onStartKafka,
    onStopKafka,
    processingStatus,
    kafkaStatus,
    devices,
}) {
    const [selectedDevice, setSelectedDevice] = useState(null);
    const [deviceData, setDeviceData] = useState(null);

    const handlePreprocessing = () => {
        if (processingStatus === "idle") {
            onStartPreprocessing();
        }
    };

    const handleKafkaToggle = () => {
        if (kafkaStatus === "stopped") {
            onStartKafka();
        } else {
            onStopKafka();
        }
    };

    const loadDeviceData = async (deviceId) => {
        try {
            const response = await fetch(
                `http://localhost:5000/api/devices/${deviceId}/data`
            );
            const data = await response.json();
            setDeviceData(data);
            setSelectedDevice(deviceId);
        } catch (error) {
            console.error("Error loading device data:", error);
        }
    };

    return (
        <div className="control-panel">
            <h2>🎮 Federated Learning Control Center</h2>

            <div className="control-grid">
                {/* Data Preprocessing Section */}
                <div className="control-card">
                    <div className="card-header">
                        <h3>📥 Data Preprocessing</h3>
                        <span className={`status-badge ${processingStatus}`}>
                            {processingStatus === "running"
                                ? "🔄 Running"
                                : "✓ Ready"}
                        </span>
                    </div>
                    <p className="card-description">
                        Run the notebook to preprocess raw data from Kaggle
                    </p>
                    <button
                        className={`btn btn-primary ${
                            processingStatus === "running" ? "disabled" : ""
                        }`}
                        onClick={handlePreprocessing}
                        disabled={processingStatus === "running"}
                    >
                        {processingStatus === "running"
                            ? "⏳ Processing..."
                            : "▶️ Start Preprocessing"}
                    </button>
                    <div className="card-info">
                        <p>Steps:</p>
                        <ul>
                            <li>Download data from Kaggle</li>
                            <li>Clean and validate</li>
                            <li>Split into device files</li>
                            <li>Save to data/processed/</li>
                        </ul>
                    </div>
                </div>

                {/* Kafka Producer Section */}
                <div className="control-card">
                    <div className="card-header">
                        <h3>📡 Kafka Streaming</h3>
                        <span className={`status-badge ${kafkaStatus}`}>
                            {kafkaStatus === "running"
                                ? "🟢 Active"
                                : "🔴 Stopped"}
                        </span>
                    </div>
                    <p className="card-description">
                        Stream device data to Kafka topic for real-time
                        processing
                    </p>
                    <button
                        className={`btn ${
                            kafkaStatus === "running"
                                ? "btn-danger"
                                : "btn-success"
                        }`}
                        onClick={handleKafkaToggle}
                    >
                        {kafkaStatus === "running"
                            ? "⏹️ Stop Kafka"
                            : "▶️ Start Kafka"}
                    </button>
                    <div className="card-info">
                        <p>Configuration:</p>
                        <ul>
                            <li>Source: data/processed/</li>
                            <li>Rate: 10 msgs/sec</li>
                            <li>Topic: edge-iiot-stream</li>
                            <li>Broker: localhost:9092</li>
                        </ul>
                    </div>
                </div>

                {/* Device Visualization Section */}
                <div className="control-card">
                    <div className="card-header">
                        <h3>📊 Device Data Visualization</h3>
                        <span className="status-badge ready">
                            {devices.length} Devices
                        </span>
                    </div>
                    <p className="card-description">
                        Browse and visualize individual device data
                    </p>

                    <div className="device-selector">
                        <label>Select a Device:</label>
                        <select
                            value={selectedDevice || ""}
                            onChange={(e) => {
                                if (e.target.value) {
                                    loadDeviceData(e.target.value);
                                }
                            }}
                        >
                            <option value="">-- Choose Device --</option>
                            {devices.map((d) => (
                                <option key={d.device_id} value={d.device_id}>
                                    Device {d.device_id} ({d.samples} samples)
                                </option>
                            ))}
                        </select>
                    </div>

                    {deviceData && (
                        <div className="device-data-preview">
                            <h4>Device {selectedDevice} Data</h4>
                            <div className="data-stats">
                                <div className="stat">
                                    <strong>Total Rows:</strong>{" "}
                                    {deviceData.total_rows}
                                </div>
                                <div className="stat">
                                    <strong>Columns:</strong>{" "}
                                    {deviceData.columns.length}
                                </div>
                            </div>

                            <div className="data-table">
                                <table>
                                    <thead>
                                        <tr>
                                            {deviceData.columns
                                                .slice(0, 5)
                                                .map((col) => (
                                                    <th key={col}>{col}</th>
                                                ))}
                                            {deviceData.columns.length > 5 && (
                                                <th>...</th>
                                            )}
                                        </tr>
                                    </thead>
                                    <tbody>
                                        {deviceData.data
                                            .slice(0, 5)
                                            .map((row, idx) => (
                                                <tr key={idx}>
                                                    {deviceData.columns
                                                        .slice(0, 5)
                                                        .map((col) => (
                                                            <td key={col}>
                                                                {typeof row[
                                                                    col
                                                                ] === "number"
                                                                    ? row[
                                                                          col
                                                                      ].toFixed(
                                                                          2
                                                                      )
                                                                    : String(
                                                                          row[
                                                                              col
                                                                          ]
                                                                      ).substring(
                                                                          0,
                                                                          20
                                                                      )}
                                                            </td>
                                                        ))}
                                                    {deviceData.columns.length >
                                                        5 && <td>...</td>}
                                                </tr>
                                            ))}
                                    </tbody>
                                </table>
                            </div>
                        </div>
                    )}
                </div>

                {/* System Status Section */}
                <div className="control-card">
                    <div className="card-header">
                        <h3>🔧 System Status</h3>
                    </div>
                    <div className="status-grid">
                        <div className="status-item">
                            <div className="status-label">Preprocessing</div>
                            <div className={`status-value ${processingStatus}`}>
                                {processingStatus === "running"
                                    ? "🔄 Running"
                                    : "✓ Ready"}
                            </div>
                        </div>
                        <div className="status-item">
                            <div className="status-label">Kafka</div>
                            <div className={`status-value ${kafkaStatus}`}>
                                {kafkaStatus === "running"
                                    ? "🟢 Active"
                                    : "🔴 Stopped"}
                            </div>
                        </div>
                        <div className="status-item">
                            <div className="status-label">Devices</div>
                            <div className="status-value">{devices.length}</div>
                        </div>
                        <div className="status-item">
                            <div className="status-label">Backend</div>
                            <div className="status-value ready">🟢 Online</div>
                        </div>
                    </div>
                </div>
            </div>

            <div className="control-workflow">
                <h3>📋 Recommended Workflow</h3>
                <div className="workflow-steps">
                    <div className="step">
                        <div className="step-number">1</div>
                        <div className="step-content">
                            <h4>Start Preprocessing</h4>
                            <p>Run the notebook to download and process data</p>
                        </div>
                    </div>
                    <div className="step">
                        <div className="step-number">2</div>
                        <div className="step-content">
                            <h4>Explore Devices</h4>
                            <p>Select a device and view its data</p>
                        </div>
                    </div>
                    <div className="step">
                        <div className="step-number">3</div>
                        <div className="step-content">
                            <h4>Start Kafka</h4>
                            <p>Begin streaming device data</p>
                        </div>
                    </div>
                    <div className="step">
                        <div className="step-number">4</div>
                        <div className="step-content">
                            <h4>Run Training</h4>
                            <p>Go to Training tab to train devices</p>
                        </div>
                    </div>
                </div>
            </div>
        </div>
    );
}

export default ControlPanel;
