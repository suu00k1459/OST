# scripts/07_forecast_metrics.py

from forecast_logging import log_forecast_run

def main():
    # 1) Load time-series from TimescaleDB or wherever
    # ts_index, actual_values = ...

    # 2) Train model & generate forecasts
    # model = ...
    # pred_values = model.predict(...)
    #
    # 3) Compute metrics
    # rmse_value = ...
    # mape_value = ...

    forecast_ts = ts_index              # list/array of timestamps
    actual_series = actual_values       # same length
    pred_series = pred_values           # same length

    # 4) >>> HERE YOU ADD THE CALL <<<
    log_forecast_run(
        pipeline_name="Global_Throughput_Forecast",
        model_type="LSTM",
        horizon_minutes=30,
        target_metric="throughput",
        timestamps=forecast_ts,
        actuals=actual_series,
        preds=pred_series,
        rmse=rmse_value,
        mape=mape_value,
    )

if __name__ == "__main__":
    main()
