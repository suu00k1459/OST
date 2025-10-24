import React, { useState } from "react";
import "./TrainingPanel.css";

function TrainingPanel({ devices, status, onTrainAll, onAggregate }) {
    const [isTraining, setIsTraining] = useState(false);
    const [trainingMessage, setTrainingMessage] = useState("");

    const handleTrainAll = async () => {
        setIsTraining(true);
        setTrainingMessage("Starting training on all devices...");
        try {
            await onTrainAll();
            setTrainingMessage("✓ Training started successfully!");
        } catch (error) {
            setTrainingMessage("✗ Error starting training: " + error.message);
        }
    };

    const handleAggregate = async () => {
        setIsTraining(true);
        setTrainingMessage("Aggregating models...");
        try {
            await onAggregate();
            setTrainingMessage("✓ Models aggregated successfully!");
        } catch (error) {
            setTrainingMessage("✗ Error aggregating models: " + error.message);
        } finally {
            setIsTraining(false);
        }
    };

    const trainedDevices = (devices || []).filter((d) => d.training_rounds > 0);
    const trainingDevices = (devices || []).filter(
        (d) => d.status === "training"
    );

    return (
        <div className="training-panel">
            <div className="training-overview">
                <div className="overview-card">
                    <h3>Training Overview</h3>
                    <div className="overview-stats">
                        <div className="overview-stat">
                            <span className="stat-label">Total Devices</span>
                            <span className="stat-value">
                                {status?.total_devices || 0}
                            </span>
                        </div>
                        <div className="overview-stat">
                            <span className="stat-label">Ready to Train</span>
                            <span className="stat-value">
                                {status?.connected_devices || 0}
                            </span>
                        </div>
                        <div className="overview-stat">
                            <span className="stat-label">
                                Currently Training
                            </span>
                            <span
                                className="stat-value"
                                style={{ color: "#f59e0b" }}
                            >
                                {trainingDevices.length}
                            </span>
                        </div>
                        <div className="overview-stat">
                            <span className="stat-label">
                                Training Completed
                            </span>
                            <span
                                className="stat-value"
                                style={{ color: "#10b981" }}
                            >
                                {trainedDevices.length}
                            </span>
                        </div>
                    </div>
                </div>
            </div>

            <div className="training-controls">
                <div className="control-card">
                    <h3>🎯 Training Controls</h3>
                    <p className="description">
                        Manage federated learning training rounds across all
                        devices
                    </p>

                    <div className="control-section">
                        <h4>Train All Devices</h4>
                        <p className="section-description">
                            Start a new training round on all connected devices
                            simultaneously
                        </p>
                        <button
                            className="primary-button train-all-btn"
                            onClick={handleTrainAll}
                            disabled={isTraining}
                        >
                            {isTraining
                                ? "⏳ Training in Progress..."
                                : "🚀 Train All Devices"}
                        </button>
                    </div>

                    <div className="divider"></div>

                    <div className="control-section">
                        <h4>Aggregate Models</h4>
                        <p className="section-description">
                            Send all local model updates to the global server
                            and perform federated averaging
                        </p>
                        <button
                            className="secondary-button aggregate-btn"
                            onClick={handleAggregate}
                            disabled={isTraining || trainedDevices.length === 0}
                        >
                            {isTraining
                                ? "⏳ Processing..."
                                : "🔄 Send Models to Global Server"}
                        </button>
                        {trainedDevices.length === 0 && (
                            <p className="info-text">
                                ⚠️ Train at least one device before aggregating
                            </p>
                        )}
                    </div>

                    {trainingMessage && (
                        <div
                            className={`message ${
                                trainingMessage.startsWith("✓")
                                    ? "success"
                                    : "error"
                            }`}
                        >
                            {trainingMessage}
                        </div>
                    )}
                </div>
            </div>

            <div className="training-details">
                <div className="detail-card">
                    <h3>📊 Training Details</h3>
                    <div className="details-grid">
                        <div className="detail-item">
                            <span className="detail-label">Current Round</span>
                            <span className="detail-value">
                                {status?.training_round || 0}
                            </span>
                        </div>
                        <div className="detail-item">
                            <span className="detail-label">
                                Global Models Saved
                            </span>
                            <span className="detail-value">
                                {status?.global_models_count || 0}
                            </span>
                        </div>
                        <div className="detail-item">
                            <span className="detail-label">
                                Average Accuracy
                            </span>
                            <span className="detail-value">
                                {(status?.average_accuracy || 0).toFixed(4)}
                            </span>
                        </div>
                        <div className="detail-item">
                            <span className="detail-label">
                                Total Data Samples
                            </span>
                            <span className="detail-value">
                                {(
                                    status?.total_data_samples || 0
                                ).toLocaleString()}
                            </span>
                        </div>
                    </div>
                </div>

                <div className="detail-card">
                    <h3>📋 Process Flow</h3>
                    <div className="process-flow">
                        <div className="flow-step completed">
                            <span className="step-number">1</span>
                            <span className="step-name">Device Discovery</span>
                        </div>
                        <div className="flow-arrow">→</div>
                        <div
                            className={`flow-step ${
                                trainedDevices.length > 0
                                    ? "completed"
                                    : "pending"
                            }`}
                        >
                            <span className="step-number">2</span>
                            <span className="step-name">Local Training</span>
                        </div>
                        <div className="flow-arrow">→</div>
                        <div className="flow-step">
                            <span className="step-number">3</span>
                            <span className="step-name">Model Aggregation</span>
                        </div>
                        <div className="flow-arrow">→</div>
                        <div className="flow-step">
                            <span className="step-number">4</span>
                            <span className="step-name">
                                Global Model Update
                            </span>
                        </div>
                    </div>
                </div>
            </div>

            <div className="device-list">
                <h3>🖥️ Device Training Status</h3>
                <div className="list-container">
                    <div className="list-section">
                        <h4>Currently Training ({trainingDevices.length})</h4>
                        {trainingDevices.length === 0 ? (
                            <p className="empty-message">
                                No devices currently training
                            </p>
                        ) : (
                            <ul className="device-list-items">
                                {trainingDevices.map((device) => (
                                    <li
                                        key={device.device_id}
                                        className="list-item training"
                                    >
                                        <span className="device-icon">🚀</span>
                                        <span className="device-name">
                                            {device.name}
                                        </span>
                                        <span className="device-progress">
                                            {device.training_progress}%
                                        </span>
                                    </li>
                                ))}
                            </ul>
                        )}
                    </div>

                    <div className="list-section">
                        <h4>Training Completed ({trainedDevices.length})</h4>
                        {trainedDevices.length === 0 ? (
                            <p className="empty-message">
                                No devices have completed training yet
                            </p>
                        ) : (
                            <ul className="device-list-items">
                                {trainedDevices.slice(0, 10).map((device) => (
                                    <li
                                        key={device.device_id}
                                        className="list-item completed"
                                    >
                                        <span className="device-icon">✅</span>
                                        <span className="device-name">
                                            {device.name}
                                        </span>
                                        <span className="device-accuracy">
                                            {(device.accuracy * 100).toFixed(1)}
                                            %
                                        </span>
                                    </li>
                                ))}
                                {trainedDevices.length > 10 && (
                                    <li className="list-item more">
                                        <span>
                                            ... and {trainedDevices.length - 10}{" "}
                                            more
                                        </span>
                                    </li>
                                )}
                            </ul>
                        )}
                    </div>
                </div>
            </div>
        </div>
    );
}

export default TrainingPanel;
