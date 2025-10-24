import React, { useState, useEffect } from "react";
import "./TrainingMonitor.css";

const API_URL = "http://localhost:5000";

function TrainingMonitor({ devices, socket }) {
    const [trainedDevices, setTrainedDevices] = useState(new Set());
    const [trainingDevices, setTrainingDevices] = useState(new Set());
    const [selectedDevice, setSelectedDevice] = useState(null);
    const [deviceNeuralNet, setDeviceNeuralNet] = useState(null);
    const [modelWeights, setModelWeights] = useState(null);
    const [overallProgress, setOverallProgress] = useState(0);
    const [trainingMode, setTrainingMode] = useState("single"); // single or all
    const [isTraining, setIsTraining] = useState(false);

    useEffect(() => {
        if (socket) {
            socket.on("device_training_start", (data) => {
                setTrainingDevices(
                    (prev) => new Set([...prev, data.device_id])
                );
            });
            socket.on("device_trained", (data) => {
                setTrainedDevices((prev) => new Set([...prev, data.device_id]));
                setTrainingDevices(
                    (prev) =>
                        new Set([...prev].filter((d) => d !== data.device_id))
                );
                setModelWeights(data.weights || null);
            });
            socket.on("training_progress", (data) => {
                setOverallProgress(data.progress);
            });
        }
    }, [socket]);

    const trainSingleDevice = async (deviceId) => {
        try {
            const response = await fetch(
                `${API_URL}/api/training/train-device/${deviceId}`,
                {
                    method: "POST",
                }
            );
            if (response.ok) {
                setTrainingDevices((prev) => new Set([...prev, deviceId]));
            }
        } catch (error) {
            console.error("Error training device:", error);
        }
    };

    const trainAllDevices = async () => {
        setIsTraining(true);
        try {
            const response = await fetch(`${API_URL}/api/training/train-all`, {
                method: "POST",
            });
            if (response.ok) {
                // Training will progress via WebSocket updates
            }
        } catch (error) {
            console.error("Error training all devices:", error);
        }
    };

    const loadDeviceModel = async (deviceId) => {
        try {
            const response = await fetch(
                `${API_URL}/api/training/device/${deviceId}/model`
            );
            const data = await response.json();
            setDeviceNeuralNet(data.architecture);
            setModelWeights(data.weights);
            setSelectedDevice(deviceId);
        } catch (error) {
            console.error("Error loading device model:", error);
        }
    };

    const sendUpdatesToServer = async () => {
        try {
            const response = await fetch(`${API_URL}/api/training/aggregate`, {
                method: "POST",
                headers: { "Content-Type": "application/json" },
                body: JSON.stringify({
                    device_weights: Array.from(trainedDevices),
                }),
            });

            if (response.ok) {
                const data = await response.json();
                console.log("Model aggregation result:", data);
            }
        } catch (error) {
            console.error("Error sending updates:", error);
        }
    };

    return (
        <div className="training-monitor">
            <div className="training-header">
                <h2>🎯 Local Training & Model Updates</h2>
                <p>
                    Train individual devices or all at once with progress
                    tracking
                </p>
            </div>

            <div className="training-layout">
                <div className="training-control-panel">
                    <h3>🎮 Training Control</h3>

                    <div className="training-mode">
                        <label>
                            <input
                                type="radio"
                                name="mode"
                                value="single"
                                checked={trainingMode === "single"}
                                onChange={(e) =>
                                    setTrainingMode(e.target.value)
                                }
                            />
                            Train Single Device
                        </label>
                        <label>
                            <input
                                type="radio"
                                name="mode"
                                value="all"
                                checked={trainingMode === "all"}
                                onChange={(e) =>
                                    setTrainingMode(e.target.value)
                                }
                            />
                            Train All Devices
                        </label>
                    </div>

                    {trainingMode === "single" ? (
                        <div className="single-training">
                            <h4>Select Device to Train</h4>
                            <div className="devices-select">
                                {devices &&
                                    devices.slice(0, 20).map((device) => (
                                        <button
                                            key={device.device_id}
                                            className={`device-btn ${
                                                trainingDevices.has(
                                                    device.device_id
                                                )
                                                    ? "training"
                                                    : trainedDevices.has(
                                                          device.device_id
                                                      )
                                                    ? "trained"
                                                    : ""
                                            }`}
                                            onClick={() =>
                                                trainSingleDevice(
                                                    device.device_id
                                                )
                                            }
                                            disabled={trainingDevices.has(
                                                device.device_id
                                            )}
                                        >
                                            {trainingDevices.has(
                                                device.device_id
                                            ) && "⏳"}
                                            {trainedDevices.has(
                                                device.device_id
                                            ) && "✅"}
                                            {!trainingDevices.has(
                                                device.device_id
                                            ) &&
                                                !trainedDevices.has(
                                                    device.device_id
                                                ) &&
                                                "▶️"}
                                            Device {device.device_id}
                                        </button>
                                    ))}
                            </div>
                        </div>
                    ) : (
                        <div className="all-training">
                            <button
                                className="btn-train-all"
                                onClick={trainAllDevices}
                                disabled={isTraining}
                            >
                                {isTraining
                                    ? "⏳ Training All..."
                                    : "▶️ Train All Devices"}
                            </button>
                            <div className="progress-section">
                                <div className="progress-label">
                                    Overall Progress:{" "}
                                    {overallProgress.toFixed(0)}%
                                </div>
                                <div className="progress-bar">
                                    <div
                                        className="progress-fill"
                                        style={{ width: `${overallProgress}%` }}
                                    ></div>
                                </div>
                            </div>
                            <div className="training-stats">
                                <div className="stat">
                                    <span className="label">Trained:</span>
                                    <span className="value">
                                        {trainedDevices.size}
                                    </span>
                                </div>
                                <div className="stat">
                                    <span className="label">Training:</span>
                                    <span className="value">
                                        {trainingDevices.size}
                                    </span>
                                </div>
                                <div className="stat">
                                    <span className="label">Remaining:</span>
                                    <span className="value">
                                        {(devices?.length || 0) -
                                            trainedDevices.size -
                                            trainingDevices.size}
                                    </span>
                                </div>
                            </div>
                        </div>
                    )}

                    <div className="aggregation-section">
                        <h4>📤 Model Aggregation</h4>
                        <button
                            className="btn-aggregate"
                            onClick={sendUpdatesToServer}
                            disabled={trainedDevices.size === 0}
                        >
                            📤 Send Updates to Global Server (
                            {trainedDevices.size} devices)
                        </button>
                        <p className="hint">
                            This will perform federated averaging on the server
                        </p>
                    </div>
                </div>

                <div className="neural-net-panel">
                    <h3>🧠 Neural Network Architecture</h3>

                    {selectedDevice && (
                        <div className="model-info">
                            <h4>Device {selectedDevice} Model</h4>

                            {deviceNeuralNet && (
                                <div className="architecture">
                                    <div className="arch-item input-layer">
                                        <span>📥</span>
                                        <span>Input Layer</span>
                                        <span>
                                            ({deviceNeuralNet.input_size}{" "}
                                            features)
                                        </span>
                                    </div>

                                    {deviceNeuralNet.layers &&
                                        deviceNeuralNet.layers.map(
                                            (layer, idx) => (
                                                <div
                                                    key={idx}
                                                    className="arch-item hidden-layer"
                                                >
                                                    <span>🔵</span>
                                                    <span>{layer.name}</span>
                                                    <span>
                                                        ({layer.units} neurons)
                                                    </span>
                                                </div>
                                            )
                                        )}

                                    <div className="arch-item output-layer">
                                        <span>📤</span>
                                        <span>Output Layer</span>
                                        <span>
                                            ({deviceNeuralNet.output_size}{" "}
                                            outputs)
                                        </span>
                                    </div>
                                </div>
                            )}

                            {modelWeights && (
                                <div className="model-weights">
                                    <h5>📊 Model Weights Summary</h5>
                                    <div className="weights-display">
                                        {Object.entries(modelWeights)
                                            .slice(0, 5)
                                            .map(([layer, shape], idx) => (
                                                <div
                                                    key={idx}
                                                    className="weight-item"
                                                >
                                                    <span className="layer-name">
                                                        {layer}
                                                    </span>
                                                    <span className="layer-shape">
                                                        {shape}
                                                    </span>
                                                </div>
                                            ))}
                                    </div>
                                </div>
                            )}
                        </div>
                    )}

                    {!selectedDevice && (
                        <div className="no-model-selected">
                            <p>Select a device to view its neural network</p>
                        </div>
                    )}

                    <div className="device-model-selector">
                        <h5>View Model From Device:</h5>
                        <select
                            onChange={(e) =>
                                loadDeviceModel(parseInt(e.target.value))
                            }
                        >
                            <option value="">Select device...</option>
                            {devices &&
                                devices.slice(0, 20).map((device) => (
                                    <option
                                        key={device.device_id}
                                        value={device.device_id}
                                    >
                                        Device {device.device_id}
                                    </option>
                                ))}
                        </select>
                    </div>
                </div>
            </div>
        </div>
    );
}

export default TrainingMonitor;
