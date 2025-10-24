import React from "react";
import {
    BarChart,
    Bar,
    LineChart,
    Line,
    PieChart,
    Pie,
    Cell,
    XAxis,
    YAxis,
    CartesianGrid,
    Tooltip,
    Legend,
    ResponsiveContainer,
} from "recharts";
import "./Dashboard.css";

function Dashboard({ status, devices }) {
    const getDevicesByStatus = () => {
        if (!devices || devices.length === 0) return [];

        const statusCounts = {
            idle: 0,
            training: 0,
            completed: 0,
            error: 0,
        };

        devices.forEach((device) => {
            const status = device.status || "idle";
            if (status in statusCounts) {
                statusCounts[status]++;
            }
        });

        return [
            { name: "Idle", value: statusCounts.idle, color: "#6366f1" },
            {
                name: "Training",
                value: statusCounts.training,
                color: "#f59e0b",
            },
            {
                name: "Completed",
                value: statusCounts.completed,
                color: "#10b981",
            },
            { name: "Error", value: statusCounts.error, color: "#ef4444" },
        ];
    };

    const getAccuracyDistribution = () => {
        if (!devices || devices.length === 0) return [];

        const bins = [
            { range: "0-0.2", count: 0 },
            { range: "0.2-0.4", count: 0 },
            { range: "0.4-0.6", count: 0 },
            { range: "0.6-0.8", count: 0 },
            { range: "0.8-1.0", count: 0 },
        ];

        devices.forEach((device) => {
            const acc = device.accuracy || 0;
            if (acc < 0.2) bins[0].count++;
            else if (acc < 0.4) bins[1].count++;
            else if (acc < 0.6) bins[2].count++;
            else if (acc < 0.8) bins[3].count++;
            else bins[4].count++;
        });

        return bins;
    };

    const statusData = getDevicesByStatus();
    const accuracyData = getAccuracyDistribution();

    const COLORS = ["#6366f1", "#f59e0b", "#10b981", "#ef4444"];

    return (
        <div className="dashboard">
            <div className="dashboard-grid">
                {/* Key Metrics */}
                <div className="metrics-row">
                    <div className="metric-card">
                        <h3>Total Devices</h3>
                        <p className="metric-value">
                            {status?.total_devices || 0}
                        </p>
                        <p className="metric-label">Across all locations</p>
                    </div>
                    <div className="metric-card">
                        <h3>Connected</h3>
                        <p className="metric-value">
                            {status?.connected_devices || 0}
                        </p>
                        <p className="metric-label">Currently online</p>
                    </div>
                    <div className="metric-card">
                        <h3>Training</h3>
                        <p className="metric-value">
                            {status?.training_devices || 0}
                        </p>
                        <p className="metric-label">In progress</p>
                    </div>
                    <div className="metric-card">
                        <h3>Trained</h3>
                        <p className="metric-value">
                            {status?.devices_trained || 0}
                        </p>
                        <p className="metric-label">Completed rounds</p>
                    </div>
                    <div className="metric-card">
                        <h3>Training Round</h3>
                        <p className="metric-value">
                            {status?.training_round || 0}
                        </p>
                        <p className="metric-label">Current global round</p>
                    </div>
                    <div className="metric-card">
                        <h3>Avg Accuracy</h3>
                        <p className="metric-value">
                            {(status?.average_accuracy || 0).toFixed(3)}
                        </p>
                        <p className="metric-label">Model performance</p>
                    </div>
                </div>

                {/* Charts */}
                <div className="charts-row">
                    <div className="chart-container full-width">
                        <h3>Device Status Distribution</h3>
                        <ResponsiveContainer width="100%" height={300}>
                            <PieChart>
                                <Pie
                                    data={statusData}
                                    cx="50%"
                                    cy="50%"
                                    labelLine={false}
                                    label={({ name, value }) =>
                                        `${name}: ${value}`
                                    }
                                    outerRadius={100}
                                    fill="#8884d8"
                                    dataKey="value"
                                >
                                    {statusData.map((entry, index) => (
                                        <Cell
                                            key={`cell-${index}`}
                                            fill={entry.color}
                                        />
                                    ))}
                                </Pie>
                                <Tooltip />
                            </PieChart>
                        </ResponsiveContainer>
                    </div>
                </div>

                <div className="charts-row">
                    <div className="chart-container">
                        <h3>Accuracy Distribution</h3>
                        <ResponsiveContainer width="100%" height={250}>
                            <BarChart data={accuracyData}>
                                <CartesianGrid
                                    strokeDasharray="3 3"
                                    stroke="rgba(255,255,255,0.1)"
                                />
                                <XAxis dataKey="range" />
                                <YAxis />
                                <Tooltip
                                    contentStyle={{
                                        backgroundColor: "rgba(0, 0, 0, 0.8)",
                                        border: "none",
                                        borderRadius: "8px",
                                    }}
                                />
                                <Bar dataKey="count" fill="#10b981" />
                            </BarChart>
                        </ResponsiveContainer>
                    </div>

                    <div className="chart-container">
                        <h3>Data Samples</h3>
                        <div className="info-box">
                            <p className="info-value">
                                {(
                                    status?.total_data_samples || 0
                                ).toLocaleString()}
                            </p>
                            <p className="info-label">
                                Total samples across all devices
                            </p>
                            <hr className="divider" />
                            <p className="info-label">Average per device:</p>
                            <p className="info-value">
                                {status?.total_devices > 0
                                    ? (
                                          (status?.total_data_samples || 0) /
                                          status?.total_devices
                                      ).toFixed(0)
                                    : 0}
                            </p>
                        </div>
                    </div>
                </div>
            </div>
        </div>
    );
}

export default Dashboard;
