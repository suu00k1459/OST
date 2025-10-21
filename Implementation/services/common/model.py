from tensorflow import keras

def build_model(input_dim: int, num_classes: int):
    model = keras.Sequential([
        keras.layers.Input(shape=(input_dim,)),
        keras.layers.Dense(128, activation="relu"),
        keras.layers.Dropout(0.2),
        keras.layers.Dense(64, activation="relu"),
        keras.layers.Dense(num_classes if num_classes > 2 else 1,
                           activation="softmax" if num_classes > 2 else "sigmoid"),
    ])
    if num_classes > 2:
        loss = "sparse_categorical_crossentropy"
        metrics = ["accuracy"]
    else:
        loss = "binary_crossentropy"
        metrics = ["accuracy", keras.metrics.AUC(name="auc")]
    model.compile(optimizer=keras.optimizers.Adam(1e-3), loss=loss, metrics=metrics)
    return model