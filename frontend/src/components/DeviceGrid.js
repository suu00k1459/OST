import React, { useState, useMemo } from "react";
import "./DeviceGrid.css";

function DeviceGrid({ devices, onTrainDevice, status }) {
    const [sortBy, setSortBy] = useState("id");
    const [filterStatus, setFilterStatus] = useState("all");
    const [searchTerm, setSearchTerm] = useState("");
    const [currentPage, setCurrentPage] = useState(1);
    const itemsPerPage = 20;

    const filteredAndSorted = useMemo(() => {
        let filtered = devices || [];

        // Filter by status
        if (filterStatus !== "all") {
            filtered = filtered.filter((d) => d.status === filterStatus);
        }

        // Search
        if (searchTerm) {
            filtered = filtered.filter(
                (d) =>
                    d.device_id.includes(searchTerm) ||
                    d.name.includes(searchTerm)
            );
        }

        // Sort
        filtered.sort((a, b) => {
            switch (sortBy) {
                case "id":
                    return a.device_id.localeCompare(b.device_id);
                case "accuracy":
                    return b.accuracy - a.accuracy;
                case "loss":
                    return a.loss - b.loss;
                case "status":
                    return a.status.localeCompare(b.status);
                default:
                    return 0;
            }
        });

        return filtered;
    }, [devices, sortBy, filterStatus, searchTerm]);

    const totalPages = Math.ceil(filteredAndSorted.length / itemsPerPage);
    const paginatedDevices = filteredAndSorted.slice(
        (currentPage - 1) * itemsPerPage,
        currentPage * itemsPerPage
    );

    const getStatusColor = (status) => {
        switch (status) {
            case "idle":
                return "#6366f1";
            case "training":
                return "#f59e0b";
            case "completed":
                return "#10b981";
            case "error":
                return "#ef4444";
            default:
                return "#999";
        }
    };

    const getStatusIcon = (status) => {
        switch (status) {
            case "idle":
                return "⏸️";
            case "training":
                return "🚀";
            case "completed":
                return "✅";
            case "error":
                return "❌";
            default:
                return "❓";
        }
    };

    return (
        <div className="device-grid-container">
            <div className="grid-controls">
                <div className="search-box">
                    <input
                        type="text"
                        placeholder="Search devices..."
                        value={searchTerm}
                        onChange={(e) => {
                            setSearchTerm(e.target.value);
                            setCurrentPage(1);
                        }}
                    />
                </div>

                <div className="filter-controls">
                    <select
                        value={filterStatus}
                        onChange={(e) => {
                            setFilterStatus(e.target.value);
                            setCurrentPage(1);
                        }}
                    >
                        <option value="all">All Status</option>
                        <option value="idle">Idle</option>
                        <option value="training">Training</option>
                        <option value="completed">Completed</option>
                        <option value="error">Error</option>
                    </select>

                    <select
                        value={sortBy}
                        onChange={(e) => setSortBy(e.target.value)}
                    >
                        <option value="id">Sort by ID</option>
                        <option value="accuracy">Sort by Accuracy</option>
                        <option value="loss">Sort by Loss</option>
                        <option value="status">Sort by Status</option>
                    </select>
                </div>

                <div className="result-info">
                    Showing {paginatedDevices.length} of{" "}
                    {filteredAndSorted.length} devices
                </div>
            </div>

            <div className="devices-grid">
                {paginatedDevices.map((device) => (
                    <div key={device.device_id} className="device-card">
                        <div className="device-header">
                            <div className="device-id">
                                <span className="status-icon">
                                    {getStatusIcon(device.status)}
                                </span>
                                <h4>{device.name}</h4>
                            </div>
                            <span
                                className="status-badge"
                                style={{
                                    backgroundColor: getStatusColor(
                                        device.status
                                    ),
                                }}
                            >
                                {device.status}
                            </span>
                        </div>

                        <div className="device-stats">
                            <div className="stat">
                                <span className="stat-label">Accuracy</span>
                                <span className="stat-value">
                                    {(device.accuracy || 0).toFixed(4)}
                                </span>
                            </div>
                            <div className="stat">
                                <span className="stat-label">Loss</span>
                                <span className="stat-value">
                                    {(device.loss || 0).toFixed(4)}
                                </span>
                            </div>
                        </div>

                        <div className="device-details">
                            <p>
                                <strong>Rounds:</strong>{" "}
                                {device.training_rounds}
                            </p>
                            <p>
                                <strong>Samples:</strong> {device.data_samples}
                            </p>
                            <p>
                                <strong>Last Seen:</strong>{" "}
                                {new Date(
                                    device.last_seen
                                ).toLocaleTimeString()}
                            </p>
                        </div>

                        <div className="device-progress">
                            {device.training_progress > 0 &&
                                device.training_progress < 100 && (
                                    <div className="progress-bar">
                                        <div
                                            className="progress-fill"
                                            style={{
                                                width: `${device.training_progress}%`,
                                            }}
                                        ></div>
                                    </div>
                                )}
                        </div>

                        {device.training_error && (
                            <div className="error-message">
                                <strong>Error:</strong> {device.training_error}
                            </div>
                        )}

                        <button
                            className="train-button"
                            onClick={() => onTrainDevice(device.device_id)}
                            disabled={device.status === "training"}
                        >
                            {device.status === "training"
                                ? "Training..."
                                : "Train Device"}
                        </button>
                    </div>
                ))}
            </div>

            {totalPages > 1 && (
                <div className="pagination">
                    <button
                        onClick={() =>
                            setCurrentPage(Math.max(1, currentPage - 1))
                        }
                        disabled={currentPage === 1}
                    >
                        ← Previous
                    </button>
                    <span className="page-info">
                        Page {currentPage} of {totalPages}
                    </span>
                    <button
                        onClick={() =>
                            setCurrentPage(
                                Math.min(totalPages, currentPage + 1)
                            )
                        }
                        disabled={currentPage === totalPages}
                    >
                        Next →
                    </button>
                </div>
            )}
        </div>
    );
}

export default DeviceGrid;
