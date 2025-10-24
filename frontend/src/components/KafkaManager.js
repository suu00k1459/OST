import React, { useState, useEffect } from "react";
import "./KafkaManager.css";

const API_URL = "http://localhost:5000";

function KafkaManager({ socket }) {
    const [kafkaStatus, setKafkaStatus] = useState("stopped");
    const [dockerContainers, setDockerContainers] = useState([]);
    const [kafkaLogs, setKafkaLogs] = useState([]);
    const [isLoading, setIsLoading] = useState(false);
    const [kafkaConfig, setKafkaConfig] = useState({});

    useEffect(() => {
        loadKafkaStatus();
        loadDockerContainers();
        const interval = setInterval(() => {
            loadKafkaStatus();
            loadDockerContainers();
        }, 3000);

        if (socket) {
            socket.on("kafka_log", (data) => {
                setKafkaLogs((prev) => [...prev.slice(-99), data]);
            });
            socket.on("kafka_status_change", (data) => {
                setKafkaStatus(data.status);
            });
        }

        return () => clearInterval(interval);
    }, [socket]);

    const loadKafkaStatus = async () => {
        try {
            const response = await fetch(`${API_URL}/api/kafka/status`);
            const data = await response.json();
            setKafkaStatus(data.status);
            setKafkaConfig(data.config || {});
        } catch (error) {
            console.error("Error loading Kafka status:", error);
        }
    };

    const loadDockerContainers = async () => {
        try {
            const response = await fetch(`${API_URL}/api/docker/containers`);
            const data = await response.json();
            setDockerContainers(data.containers || []);
        } catch (error) {
            console.error("Error loading Docker containers:", error);
        }
    };

    const startKafka = async () => {
        setIsLoading(true);
        try {
            const response = await fetch(`${API_URL}/api/kafka/start`, {
                method: "POST",
            });
            if (response.ok) {
                setKafkaStatus("starting");
            }
        } catch (error) {
            console.error("Error starting Kafka:", error);
        } finally {
            setIsLoading(false);
        }
    };

    const stopKafka = async () => {
        setIsLoading(true);
        try {
            const response = await fetch(`${API_URL}/api/kafka/stop`, {
                method: "POST",
            });
            if (response.ok) {
                setKafkaStatus("stopping");
            }
        } catch (error) {
            console.error("Error stopping Kafka:", error);
        } finally {
            setIsLoading(false);
        }
    };

    return (
        <div className="kafka-manager">
            <div className="kafka-header">
                <h2>📡 Kafka & Docker Management</h2>
            </div>

            <div className="kafka-layout">
                <div className="kafka-section left">
                    <div className="kafka-control-panel">
                        <h3>🔧 Kafka Control</h3>
                        <div className="kafka-status-display">
                            <div className={`status-badge ${kafkaStatus}`}>
                                {kafkaStatus === "running" && "🟢 Running"}
                                {kafkaStatus === "stopped" && "🔴 Stopped"}
                                {kafkaStatus === "starting" && "🟡 Starting..."}
                                {kafkaStatus === "stopping" && "🟠 Stopping..."}
                            </div>
                        </div>

                        <div className="kafka-buttons">
                            <button
                                className="btn-start"
                                onClick={startKafka}
                                disabled={
                                    kafkaStatus === "running" || isLoading
                                }
                            >
                                {isLoading ? "⏳..." : "▶️ Start Kafka"}
                            </button>
                            <button
                                className="btn-stop"
                                onClick={stopKafka}
                                disabled={
                                    kafkaStatus === "stopped" || isLoading
                                }
                            >
                                {isLoading ? "⏳..." : "⏹️ Stop Kafka"}
                            </button>
                        </div>

                        <div className="kafka-config">
                            <h4>Configuration</h4>
                            <div className="config-item">
                                <span>Broker:</span>
                                <code>
                                    {kafkaConfig.broker || "localhost:9092"}
                                </code>
                            </div>
                            <div className="config-item">
                                <span>Topic:</span>
                                <code>
                                    {kafkaConfig.topic || "sensor-data"}
                                </code>
                            </div>
                            <div className="config-item">
                                <span>Rate:</span>
                                <code>{kafkaConfig.rate || "1000ms"}</code>
                            </div>
                        </div>
                    </div>
                </div>

                <div className="kafka-section right">
                    <div className="docker-containers">
                        <h3>🐳 Running Docker Containers</h3>
                        <div className="containers-list">
                            {dockerContainers.length > 0 ? (
                                dockerContainers.map((container, idx) => (
                                    <div key={idx} className="container-item">
                                        <div className="container-header">
                                            <span className="container-name">
                                                {container.name}
                                            </span>
                                            <span
                                                className={`container-status ${container.state}`}
                                            >
                                                {container.state === "running"
                                                    ? "🟢"
                                                    : "🔴"}{" "}
                                                {container.state}
                                            </span>
                                        </div>
                                        <div className="container-details">
                                            <small>
                                                Image: {container.image}
                                            </small>
                                            <small>
                                                ID:{" "}
                                                {container.id.substring(0, 12)}
                                            </small>
                                        </div>
                                    </div>
                                ))
                            ) : (
                                <div className="empty-state">
                                    No running containers
                                </div>
                            )}
                        </div>
                    </div>

                    <div className="kafka-logs">
                        <h3>📜 Kafka Logs</h3>
                        <div className="logs-display">
                            {kafkaLogs.length > 0 ? (
                                kafkaLogs.map((log, idx) => (
                                    <div key={idx} className="log-line">
                                        {log}
                                    </div>
                                ))
                            ) : (
                                <div className="empty-state">
                                    No logs yet...
                                </div>
                            )}
                        </div>
                    </div>
                </div>
            </div>
        </div>
    );
}

export default KafkaManager;
