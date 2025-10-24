import React, { useState, useEffect } from "react";
import axios from "axios";
import io from "socket.io-client";
import "./PipelineControl.css";

const API_URL = "http://localhost:5000";

function PipelineControl() {
    const [step, setStep] = useState(1);
    const [devices, setDevices] = useState([]);
    const [deviceCount, setDeviceCount] = useState(0);
    const [totalSamples, setTotalSamples] = useState(0);
    const [loading, setLoading] = useState(false);
    const [message, setMessage] = useState("");
    const [trainingMode, setTrainingMode] = useState("all");
    const [specificDeviceId, setSpecificDeviceId] = useState("");
    const [rangeStart, setRangeStart] = useState(0);
    const [rangeEnd, setRangeEnd] = useState(100);
    const [progress, setProgress] = useState({});
    const [training, setTraining] = useState(false);
    const socketRef = React.useRef(null);

    useEffect(() => {
        socketRef.current = io(API_URL);

        socketRef.current.on("devices_loaded_from_csv", (data) => {
            setMessage(
                `✅ Loaded ${data.device_count} devices with ${(
                    data.total_samples / 1e6
                ).toFixed(1)}M total samples`
            );
        });

        return () => socketRef.current?.disconnect();
    }, []);

    const handleLoadData = async () => {
        setLoading(true);
        setMessage("Scanning CSV directory...");

        try {
            const scanResponse = await axios.get(
                `${API_URL}/api/training/devices-from-csv`
            );
            const {
                device_count,
                devices: devList,
                total_data_samples,
            } = scanResponse.data;

            setDeviceCount(device_count);
            setDevices(devList);
            setTotalSamples(total_data_samples);

            const loadResponse = await axios.post(
                `${API_URL}/api/training/load-csv-devices`
            );

            setMessage(
                `✅ Success! Found ${device_count} devices with ${(
                    total_data_samples / 1e6
                ).toFixed(1)}M samples`
            );
            setStep(2);
        } catch (error) {
            setMessage(
                `❌ Error: ${error.response?.data?.message || error.message}`
            );
        } finally {
            setLoading(false);
        }
    };

    const handleStartTraining = async () => {
        setTraining(true);
        setMessage("Starting training...");
        setProgress({});

        try {
            let endpoint = `${API_URL}/api/training/train-all`;
            let payload = {};

            if (trainingMode === "specific") {
                endpoint = `${API_URL}/api/training/train-device`;
                payload = { device_id: specificDeviceId };
            } else if (trainingMode === "range") {
                endpoint = `${API_URL}/api/training/train-range`;
                payload = { start: rangeStart, end: rangeEnd };
            }

            const response = await axios.post(endpoint, payload);
            setMessage(
                `🚀 Training started! Job ID: ${
                    response.data.job_id || "Flink Job"
                }`
            );
        } catch (error) {
            setMessage(
                `❌ Error: ${error.response?.data?.message || error.message}`
            );
        } finally {
            setTraining(false);
        }
    };

    const handleAggregate = async () => {
        setLoading(true);
        setMessage("Aggregating models...");

        try {
            const response = await axios.post(
                `${API_URL}/api/aggregation/aggregate`
            );
            setMessage("✅ Models aggregated successfully!");
            setStep(4);
        } catch (error) {
            setMessage(
                `❌ Error: ${error.response?.data?.message || error.message}`
            );
        } finally {
            setLoading(false);
        }
    };

    const handleGenerateReport = async () => {
        setLoading(true);
        setMessage("Generating reports...");

        try {
            const response = await axios.get(
                `${API_URL}/api/analytics/generate-report`
            );
            setMessage("✅ Report generated!");
        } catch (error) {
            setMessage(
                `❌ Error: ${error.response?.data?.message || error.message}`
            );
        } finally {
            setLoading(false);
        }
    };

    return (
        <div className="pipeline-container">
            <h2>🚀 Federated Learning Pipeline</h2>

            {/* STEP 1: LOAD DATA */}
            <div
                className={`pipeline-step step-1 ${step >= 1 ? "active" : ""}`}
            >
                <div className="step-header">
                    <h3>Step 1: Load CSV Data</h3>
                    {step > 1 && (
                        <span className="step-badge">✅ Complete</span>
                    )}
                </div>

                <div className="step-content">
                    <p>
                        Scan the <code>notebooks/edge_iiot_processed/</code>{" "}
                        directory for device CSV files.
                    </p>

                    {deviceCount > 0 && (
                        <div className="info-box">
                            <p>
                                ✅ <strong>{deviceCount}</strong> devices found
                            </p>
                            <p>
                                📊{" "}
                                <strong>
                                    {(totalSamples / 1e6).toFixed(1)}M
                                </strong>{" "}
                                total samples
                            </p>
                        </div>
                    )}

                    <button
                        onClick={handleLoadData}
                        disabled={step !== 1 || loading}
                        className="btn btn-primary"
                    >
                        {loading ? "⏳ Scanning..." : "📂 Load Data"}
                    </button>
                </div>
            </div>

            {/* STEP 2: LOCAL TRAINING */}
            <div
                className={`pipeline-step step-2 ${step >= 2 ? "active" : ""}`}
            >
                <div className="step-header">
                    <h3>Step 2: Local Training (Flink Parallel)</h3>
                    {step > 2 && (
                        <span className="step-badge">✅ Complete</span>
                    )}
                </div>

                <div className="step-content">
                    <p>Select training scope:</p>

                    <div className="training-options">
                        <label className="option">
                            <input
                                type="radio"
                                value="all"
                                checked={trainingMode === "all"}
                                onChange={(e) =>
                                    setTrainingMode(e.target.value)
                                }
                            />
                            <span>Train All {deviceCount} Devices</span>
                        </label>

                        <label className="option">
                            <input
                                type="radio"
                                value="specific"
                                checked={trainingMode === "specific"}
                                onChange={(e) =>
                                    setTrainingMode(e.target.value)
                                }
                            />
                            <span>Train Specific Device ID:</span>
                            <input
                                type="text"
                                placeholder="e.g., device_500"
                                value={specificDeviceId}
                                onChange={(e) =>
                                    setSpecificDeviceId(e.target.value)
                                }
                                disabled={trainingMode !== "specific"}
                            />
                        </label>

                        <label className="option">
                            <input
                                type="radio"
                                value="range"
                                checked={trainingMode === "range"}
                                onChange={(e) =>
                                    setTrainingMode(e.target.value)
                                }
                            />
                            <span>Train Range:</span>
                            <div className="range-inputs">
                                <input
                                    type="number"
                                    placeholder="From"
                                    value={rangeStart}
                                    onChange={(e) =>
                                        setRangeStart(parseInt(e.target.value))
                                    }
                                    disabled={trainingMode !== "range"}
                                />
                                <span>to</span>
                                <input
                                    type="number"
                                    placeholder="To"
                                    value={rangeEnd}
                                    onChange={(e) =>
                                        setRangeEnd(parseInt(e.target.value))
                                    }
                                    disabled={trainingMode !== "range"}
                                />
                            </div>
                        </label>
                    </div>

                    <div className="progress-info">
                        <p>⚡ Speed: 15-60x faster than sequential training!</p>
                        <p>⏱️ Estimated time: 1-2 minutes for all devices</p>
                    </div>

                    <button
                        onClick={handleStartTraining}
                        disabled={step !== 2 || training || deviceCount === 0}
                        className="btn btn-primary btn-large"
                    >
                        {training
                            ? "🚀 Training in Progress..."
                            : "🚀 Start Training"}
                    </button>
                </div>
            </div>

            {/* STEP 3: MODEL AGGREGATION */}
            <div
                className={`pipeline-step step-3 ${step >= 3 ? "active" : ""}`}
            >
                <div className="step-header">
                    <h3>Step 3: Model Aggregation</h3>
                    {step > 3 && (
                        <span className="step-badge">✅ Complete</span>
                    )}
                </div>

                <div className="step-content">
                    <p>Aggregate all local models using Federated Averaging:</p>

                    <div className="aggregation-info">
                        <p>
                            📦 Models to aggregate:{" "}
                            <strong>{deviceCount}</strong>
                        </p>
                        <p>🔄 Method: Federated Averaging (Weighted Mean)</p>
                        <p>⚙️ Server will compute global model weights</p>
                    </div>

                    <button
                        onClick={handleAggregate}
                        disabled={step !== 3 || loading}
                        className="btn btn-secondary"
                    >
                        {loading ? "⏳ Aggregating..." : "🔄 Aggregate Models"}
                    </button>
                </div>
            </div>

            {/* STEP 4: VISUALIZATION */}
            <div
                className={`pipeline-step step-4 ${step >= 4 ? "active" : ""}`}
            >
                <div className="step-header">
                    <h3>Step 4: Visualization & Analytics</h3>
                </div>

                <div className="step-content">
                    <p>Generate detailed reports and visualizations:</p>

                    <div className="analytics-list">
                        <div className="analytics-item">
                            📈 Training curves per device
                        </div>
                        <div className="analytics-item">
                            📊 Accuracy distribution chart
                        </div>
                        <div className="analytics-item">
                            🔍 Device comparison matrix
                        </div>
                        <div className="analytics-item">
                            🎯 Global model metrics
                        </div>
                        <div className="analytics-item">
                            💾 Export capabilities
                        </div>
                    </div>

                    <button
                        onClick={handleGenerateReport}
                        disabled={step !== 4 || loading}
                        className="btn btn-success"
                    >
                        {loading ? "⏳ Generating..." : "📊 Generate Report"}
                    </button>
                </div>
            </div>

            {/* STATUS MESSAGE */}
            {message && (
                <div
                    className={`status-message ${
                        message.startsWith("✅")
                            ? "success"
                            : message.startsWith("❌")
                            ? "error"
                            : "info"
                    }`}
                >
                    {message}
                </div>
            )}
        </div>
    );
}

export default PipelineControl;
