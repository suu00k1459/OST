import React, { useState, useEffect } from "react";
import axios from "axios";
import "./GlobalModelPanel.css";

const API_URL = "http://localhost:5000";

function GlobalModelPanel({ globalModel, status, onAggregate }) {
    const [history, setHistory] = useState([]);
    const [loading, setLoading] = useState(false);

    useEffect(() => {
        loadHistory();
    }, []);

    const loadHistory = async () => {
        try {
            setLoading(true);
            const response = await axios.get(
                `${API_URL}/api/aggregation/history`,
                {
                    params: { limit: 20 },
                }
            );
            setHistory(response.data.history || []);
        } catch (error) {
            console.error("Error loading history:", error);
        } finally {
            setLoading(false);
        }
    };

    const handleAggregate = async () => {
        try {
            await onAggregate();
            setTimeout(loadHistory, 1000);
        } catch (error) {
            console.error("Error aggregating:", error);
        }
    };

    return (
        <div className="global-model-panel">
            <div className="current-model">
                <div className="model-card">
                    <h2>🌍 Global Model</h2>

                    {globalModel ? (
                        <div className="model-info">
                            <div className="model-header">
                                <div className="model-stats">
                                    <div className="stat">
                                        <span className="label">Round</span>
                                        <span className="value">
                                            {globalModel.round}
                                        </span>
                                    </div>
                                    <div className="stat">
                                        <span className="label">
                                            Devices Aggregated
                                        </span>
                                        <span className="value">
                                            {globalModel.device_ids?.length ||
                                                0}
                                        </span>
                                    </div>
                                    <div className="stat">
                                        <span className="label">
                                            Total Samples
                                        </span>
                                        <span className="value">
                                            {(
                                                globalModel.total_samples || 0
                                            ).toLocaleString()}
                                        </span>
                                    </div>
                                </div>
                            </div>

                            <div className="model-metrics">
                                <div className="metric-item">
                                    <h4>Global Accuracy</h4>
                                    <div className="metric-value">
                                        <span className="number">
                                            {(
                                                globalModel.accuracy * 100
                                            ).toFixed(2)}
                                            %
                                        </span>
                                        <div className="progress-bar">
                                            <div
                                                className="progress-fill"
                                                style={{
                                                    width: `${Math.min(
                                                        globalModel.accuracy *
                                                            100,
                                                        100
                                                    )}%`,
                                                }}
                                            ></div>
                                        </div>
                                    </div>
                                </div>

                                <div className="metric-item">
                                    <h4>Global Loss</h4>
                                    <div className="metric-value">
                                        <span className="number">
                                            {(globalModel.loss || 0).toFixed(4)}
                                        </span>
                                    </div>
                                </div>
                            </div>

                            {globalModel.statistics && (
                                <div className="statistics">
                                    <h4>Device Statistics</h4>
                                    <div className="stats-grid">
                                        <div className="stat-box">
                                            <span className="stat-name">
                                                Accuracy Mean
                                            </span>
                                            <span className="stat-value">
                                                {(
                                                    globalModel.statistics
                                                        .accuracy?.mean * 100
                                                ).toFixed(2)}
                                                %
                                            </span>
                                        </div>
                                        <div className="stat-box">
                                            <span className="stat-name">
                                                Accuracy Std Dev
                                            </span>
                                            <span className="stat-value">
                                                {(
                                                    globalModel.statistics
                                                        .accuracy?.std * 100
                                                ).toFixed(2)}
                                                %
                                            </span>
                                        </div>
                                        <div className="stat-box">
                                            <span className="stat-name">
                                                Accuracy Min
                                            </span>
                                            <span className="stat-value">
                                                {(
                                                    globalModel.statistics
                                                        .accuracy?.min * 100
                                                ).toFixed(2)}
                                                %
                                            </span>
                                        </div>
                                        <div className="stat-box">
                                            <span className="stat-name">
                                                Accuracy Max
                                            </span>
                                            <span className="stat-value">
                                                {(
                                                    globalModel.statistics
                                                        .accuracy?.max * 100
                                                ).toFixed(2)}
                                                %
                                            </span>
                                        </div>
                                    </div>
                                </div>
                            )}

                            <div className="model-timestamp">
                                <small>
                                    Last Updated:{" "}
                                    {new Date(
                                        globalModel.timestamp
                                    ).toLocaleString()}
                                </small>
                            </div>
                        </div>
                    ) : (
                        <div className="no-model">
                            <p>No global model available yet</p>
                            <p className="hint">
                                Train devices and aggregate their models to
                                create a global model
                            </p>
                        </div>
                    )}

                    <button
                        className="aggregate-button"
                        onClick={handleAggregate}
                        disabled={!status || status.devices_trained === 0}
                    >
                        🔄 Create/Update Global Model
                    </button>
                    {status && status.devices_trained === 0 && (
                        <p className="warning">
                            ⚠️ Train at least one device before creating a
                            global model
                        </p>
                    )}
                </div>
            </div>

            <div className="model-history">
                <div className="history-card">
                    <h2>📊 Global Model History</h2>

                    {loading ? (
                        <div className="loading">Loading history...</div>
                    ) : history.length === 0 ? (
                        <div className="empty-history">
                            <p>No global models created yet</p>
                        </div>
                    ) : (
                        <div className="history-timeline">
                            {history.map((model, index) => (
                                <div key={index} className="history-item">
                                    <div className="timeline-marker">
                                        <span className="marker-number">
                                            {model.round}
                                        </span>
                                    </div>
                                    <div className="timeline-content">
                                        <div className="content-header">
                                            <h4>Round {model.round}</h4>
                                            <span className="content-time">
                                                {new Date(
                                                    model.timestamp
                                                ).toLocaleTimeString()}
                                            </span>
                                        </div>

                                        <div className="content-metrics">
                                            <div className="metric">
                                                <span className="metric-label">
                                                    Accuracy:
                                                </span>
                                                <span className="metric-val">
                                                    {(
                                                        model.accuracy * 100
                                                    ).toFixed(2)}
                                                    %
                                                </span>
                                            </div>
                                            <div className="metric">
                                                <span className="metric-label">
                                                    Loss:
                                                </span>
                                                <span className="metric-val">
                                                    {(model.loss || 0).toFixed(
                                                        4
                                                    )}
                                                </span>
                                            </div>
                                            <div className="metric">
                                                <span className="metric-label">
                                                    Devices:
                                                </span>
                                                <span className="metric-val">
                                                    {model.device_ids?.length ||
                                                        0}
                                                </span>
                                            </div>
                                            <div className="metric">
                                                <span className="metric-label">
                                                    Samples:
                                                </span>
                                                <span className="metric-val">
                                                    {(
                                                        model.total_samples || 0
                                                    ).toLocaleString()}
                                                </span>
                                            </div>
                                        </div>
                                    </div>
                                </div>
                            ))}
                        </div>
                    )}
                </div>
            </div>

            <div className="federation-info">
                <div className="info-card">
                    <h3>ℹ️ Federated Learning Process</h3>
                    <div className="info-content">
                        <div className="info-step">
                            <span className="step-icon">1️⃣</span>
                            <div className="step-content">
                                <h4>Local Training</h4>
                                <p>
                                    Each device trains its own model locally on
                                    its data
                                </p>
                            </div>
                        </div>
                        <div className="divider"></div>
                        <div className="info-step">
                            <span className="step-icon">2️⃣</span>
                            <div className="step-content">
                                <h4>Model Aggregation</h4>
                                <p>
                                    Models are sent to the server and aggregated
                                    using federated averaging
                                </p>
                            </div>
                        </div>
                        <div className="divider"></div>
                        <div className="info-step">
                            <span className="step-icon">3️⃣</span>
                            <div className="step-content">
                                <h4>Global Model Update</h4>
                                <p>
                                    A new global model is created by averaging
                                    the local model weights
                                </p>
                            </div>
                        </div>
                        <div className="divider"></div>
                        <div className="info-step">
                            <span className="step-icon">4️⃣</span>
                            <div className="step-content">
                                <h4>Distribution</h4>
                                <p>
                                    The global model can be sent back to all
                                    devices for the next round
                                </p>
                            </div>
                        </div>
                    </div>
                </div>
            </div>
        </div>
    );
}

export default GlobalModelPanel;
