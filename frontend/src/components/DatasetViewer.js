import React, { useState, useEffect } from "react";
import "./DatasetViewer.css";

const API_URL = "http://localhost:5000";

function DatasetViewer() {
    const [rawData, setRawData] = useState([]);
    const [processedData, setProcessedData] = useState([]);
    const [activeTab, setActiveTab] = useState("raw");
    const [stats, setStats] = useState({});
    const [loading, setLoading] = useState(true);

    useEffect(() => {
        loadDatasetInfo();
    }, []);

    const loadDatasetInfo = async () => {
        setLoading(true);
        try {
            const [rawRes, procRes] = await Promise.all([
                fetch(`${API_URL}/api/dataset/raw`),
                fetch(`${API_URL}/api/dataset/processed`),
            ]);

            const rawData = await rawRes.json();
            const procData = await procRes.json();

            setRawData(rawData.files || []);
            setProcessedData(procData.files || []);
            setStats(rawData.stats || {});
        } catch (error) {
            console.error("Error loading datasets:", error);
        } finally {
            setLoading(false);
        }
    };

    return (
        <div className="dataset-viewer">
            <div className="dataset-header">
                <h2>📁 Dataset Management</h2>
                <button className="btn-refresh" onClick={loadDatasetInfo}>
                    🔄 Refresh
                </button>
            </div>

            <div className="dataset-tabs">
                <button
                    className={`tab ${activeTab === "raw" ? "active" : ""}`}
                    onClick={() => setActiveTab("raw")}
                >
                    📥 Raw Dataset
                </button>
                <button
                    className={`tab ${
                        activeTab === "processed" ? "active" : ""
                    }`}
                    onClick={() => setActiveTab("processed")}
                >
                    ⚙️ Processed Dataset
                </button>
                <button
                    className={`tab ${activeTab === "stats" ? "active" : ""}`}
                    onClick={() => setActiveTab("stats")}
                >
                    📊 Statistics
                </button>
            </div>

            <div className="dataset-content">
                {activeTab === "raw" && (
                    <div className="dataset-section">
                        <h3>📥 Raw Dataset Files (From Kaggle)</h3>
                        <div className="files-grid">
                            {rawData.length > 0 ? (
                                rawData.map((file, idx) => (
                                    <div key={idx} className="file-card">
                                        <div className="file-icon">📄</div>
                                        <div className="file-info">
                                            <div className="file-name">
                                                {file.name}
                                            </div>
                                            <div className="file-size">
                                                {file.size}
                                            </div>
                                            <div className="file-rows">
                                                {file.rows} rows
                                            </div>
                                        </div>
                                    </div>
                                ))
                            ) : (
                                <div className="empty-state">
                                    No raw dataset files found
                                </div>
                            )}
                        </div>
                    </div>
                )}

                {activeTab === "processed" && (
                    <div className="dataset-section">
                        <h3>⚙️ Processed Dataset Files (Per-Device)</h3>
                        <div className="processed-stats">
                            <div className="stat">
                                <span className="stat-label">
                                    Total Devices:
                                </span>
                                <span className="stat-value">
                                    {processedData.length}
                                </span>
                            </div>
                            {stats.total_rows && (
                                <div className="stat">
                                    <span className="stat-label">
                                        Total Rows:
                                    </span>
                                    <span className="stat-value">
                                        {stats.total_rows.toLocaleString()}
                                    </span>
                                </div>
                            )}
                        </div>
                        <div className="files-grid">
                            {processedData.slice(0, 20).map((file, idx) => (
                                <div key={idx} className="file-card">
                                    <div className="file-icon">💾</div>
                                    <div className="file-info">
                                        <div className="file-name">
                                            {file.name}
                                        </div>
                                        <div className="file-size">
                                            {file.size}
                                        </div>
                                        <div className="file-rows">
                                            {file.rows} rows
                                        </div>
                                    </div>
                                </div>
                            ))}
                        </div>
                        {processedData.length > 20 && (
                            <div className="more-files">
                                ... and {processedData.length - 20} more files
                            </div>
                        )}
                    </div>
                )}

                {activeTab === "stats" && (
                    <div className="dataset-section">
                        <h3>📊 Dataset Statistics</h3>
                        <div className="stats-grid">
                            <div className="stat-card">
                                <div className="stat-title">Raw Files</div>
                                <div className="stat-number">
                                    {rawData.length}
                                </div>
                            </div>
                            <div className="stat-card">
                                <div className="stat-title">
                                    Processed Devices
                                </div>
                                <div className="stat-number">
                                    {processedData.length}
                                </div>
                            </div>
                            <div className="stat-card">
                                <div className="stat-title">Total Rows</div>
                                <div className="stat-number">
                                    {stats.total_rows
                                        ? (stats.total_rows / 1000).toFixed(0) +
                                          "K"
                                        : "0"}
                                </div>
                            </div>
                            <div className="stat-card">
                                <div className="stat-title">Columns</div>
                                <div className="stat-number">
                                    {stats.columns || "?"}
                                </div>
                            </div>
                        </div>
                    </div>
                )}
            </div>
        </div>
    );
}

export default DatasetViewer;
