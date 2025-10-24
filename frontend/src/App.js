import React, { useState, useEffect, useRef } from "react";
import axios from "axios";
import io from "socket.io-client";
import "./App.css";
import Dashboard from "./components/Dashboard";
import DeviceGrid from "./components/DeviceGrid";
import TrainingPanel from "./components/TrainingPanel";
import GlobalModelPanel from "./components/GlobalModelPanel";
import PipelineControl from "./components/PipelineControl";

const API_URL = "http://localhost:5000";

function App() {
    const [devices, setDevices] = useState([]);
    const [status, setStatus] = useState(null);
    const [globalModel, setGlobalModel] = useState(null);
    const [loading, setLoading] = useState(true);
    const [activeTab, setActiveTab] = useState("dashboard");
    const socketRef = useRef(null);

    useEffect(() => {
        // Connect to WebSocket
        socketRef.current = io(API_URL, {
            reconnection: true,
            reconnectionDelay: 1000,
            reconnectionDelayMax: 5000,
            reconnectionAttempts: 5,
        });

        socketRef.current.on("connect", () => {
            console.log("Connected to server");
            requestDeviceList();
            requestStatus();
        });

        socketRef.current.on("device_list", (data) => {
            setDevices(data.devices || []);
        });

        socketRef.current.on("status_update", (data) => {
            setStatus(data);
        });

        socketRef.current.on("device_training_completed", (data) => {
            // Refresh device list
            requestDeviceList();
        });

        socketRef.current.on("global_model_updated", (data) => {
            setGlobalModel(data);
            requestDeviceList();
        });

        socketRef.current.on("training_started", (data) => {
            console.log("Training started:", data);
        });

        socketRef.current.on("devices_discovered", (data) => {
            console.log("Devices discovered:", data);
            requestDeviceList();
        });

        // Initial data load
        loadInitialData();

        // Polling
        const interval = setInterval(() => {
            requestDeviceList();
            requestStatus();
        }, 3000);

        return () => {
            clearInterval(interval);
            socketRef.current.disconnect();
        };
    }, []);

    const loadInitialData = async () => {
        try {
            await axios.post(`${API_URL}/api/devices/discovery/auto`);
            await requestDeviceList();
            await requestStatus();
            setLoading(false);
        } catch (error) {
            console.error("Error loading initial data:", error);
            setLoading(false);
        }
    };

    const requestDeviceList = async () => {
        try {
            const response = await axios.get(`${API_URL}/api/devices`, {
                params: { per_page: 100 },
            });
            setDevices(response.data.devices || []);
        } catch (error) {
            console.error("Error fetching devices:", error);
        }
    };

    const requestStatus = async () => {
        try {
            const response = await axios.get(`${API_URL}/api/status`);
            setStatus(response.data);
        } catch (error) {
            console.error("Error fetching status:", error);
        }
    };

    const trainDevice = async (deviceId) => {
        try {
            await axios.post(`${API_URL}/api/training/train-device`, {
                device_id: deviceId,
            });
        } catch (error) {
            console.error("Error training device:", error);
        }
    };

    const trainAllDevices = async () => {
        try {
            await axios.post(`${API_URL}/api/training/train-all`);
        } catch (error) {
            console.error("Error training all devices:", error);
        }
    };

    const aggregateModels = async () => {
        try {
            const response = await axios.post(
                `${API_URL}/api/aggregation/aggregate`
            );
            setGlobalModel(response.data.aggregated);
        } catch (error) {
            console.error("Error aggregating models:", error);
        }
    };

    if (loading) {
        return (
            <div className="app loading-container">
                <div className="loading-spinner">
                    <div className="spinner"></div>
                    <p>Initializing Federated Learning System...</p>
                </div>
            </div>
        );
    }

    return (
        <div className="app">
            <header className="app-header">
                <div className="header-content">
                    <div className="logo-section">
                        <h1>🤖 Federated Learning System</h1>
                        <p>Distributed Model Training & Aggregation</p>
                    </div>
                    <div className="header-stats">
                        {status && (
                            <>
                                <div className="stat-item">
                                    <span className="stat-label">
                                        Total Devices:
                                    </span>
                                    <span className="stat-value">
                                        {status.total_devices}
                                    </span>
                                </div>
                                <div className="stat-item">
                                    <span className="stat-label">
                                        Training Round:
                                    </span>
                                    <span className="stat-value">
                                        {status.training_round}
                                    </span>
                                </div>
                            </>
                        )}
                    </div>
                </div>
            </header>

            <div className="app-container">
                <nav className="tab-navigation">
                    <button
                        className={`tab-button ${
                            activeTab === "dashboard" ? "active" : ""
                        }`}
                        onClick={() => setActiveTab("dashboard")}
                    >
                        📊 Dashboard
                    </button>
                    <button
                        className={`tab-button ${
                            activeTab === "pipeline" ? "active" : ""
                        }`}
                        onClick={() => setActiveTab("pipeline")}
                    >
                        🚀 Pipeline
                    </button>
                    <button
                        className={`tab-button ${
                            activeTab === "devices" ? "active" : ""
                        }`}
                        onClick={() => setActiveTab("devices")}
                    >
                        🖥️ Devices ({devices.length})
                    </button>
                    <button
                        className={`tab-button ${
                            activeTab === "training" ? "active" : ""
                        }`}
                        onClick={() => setActiveTab("training")}
                    >
                        🎯 Training
                    </button>
                    <button
                        className={`tab-button ${
                            activeTab === "models" ? "active" : ""
                        }`}
                        onClick={() => setActiveTab("models")}
                    >
                        🔄 Global Model
                    </button>
                </nav>

                <main className="app-main">
                    {activeTab === "dashboard" && (
                        <Dashboard status={status} devices={devices} />
                    )}
                    {activeTab === "pipeline" && <PipelineControl />}
                    {activeTab === "devices" && (
                        <DeviceGrid
                            devices={devices}
                            onTrainDevice={trainDevice}
                            status={status}
                        />
                    )}
                    {activeTab === "training" && (
                        <TrainingPanel
                            devices={devices}
                            status={status}
                            onTrainAll={trainAllDevices}
                            onAggregate={aggregateModels}
                        />
                    )}
                    {activeTab === "models" && (
                        <GlobalModelPanel
                            globalModel={globalModel}
                            status={status}
                            onAggregate={aggregateModels}
                        />
                    )}
                </main>
            </div>

            <footer className="app-footer">
                <p>
                    © 2024 Federated Learning System | Real-time Edge
                    Intelligence
                </p>
            </footer>
        </div>
    );
}

export default App;
