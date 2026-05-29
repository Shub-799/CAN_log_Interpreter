import streamlit as st
import pandas as pd
import cantools
import plotly.express as px

st.set_page_config(page_title="CAN Log Interpreter", layout="wide")

st.title("CAN Log Interpreter")
st.write("High-performance CAN Log Decoder")

dbc_file = st.file_uploader("Upload DBC File", type=["dbc"])
log_file = st.file_uploader("Upload CAN Log File", type=["log", "txt", "asc"])

preview_rows = st.number_input(
    "Rows to display in preview",
    min_value=50,
    max_value=5000,
    value=200,
    step=50
)

max_graph_points = st.number_input(
    "Maximum graph points",
    min_value=5000,
    max_value=50000,
    value=10000,
    step=5000
)


@st.cache_data
def parse_can_log_fast(file_content):

    messages = []

    text = file_content.decode("utf-8", errors="ignore")
    lines = text.splitlines()

    for line in lines:

        if not line or line.startswith("***"):
            continue

        line_lower = line.lower()

        if (
            line_lower.startswith("date")
            or line_lower.startswith("base")
            or line_lower.startswith("begin")
            or line_lower.startswith("end")
            or "errorframe" in line_lower
            or "canfd" in line_lower
        ):
            continue

        parts = line.split()

        try:

            # BUSMASTER format
            if len(parts) >= 7 and parts[1] in ("Rx", "Tx"):

                h, m, s, ms = parts[0].split(":")

                timestamp = (
                    int(h) * 3600 +
                    int(m) * 60 +
                    int(s) +
                    int(ms) / 10000
                )

                can_id = int(parts[3], 16)

                dlc = int(parts[5])

                data_bytes = bytes.fromhex(
                    " ".join(parts[6:6 + dlc])
                )

                messages.append(
                    (timestamp, can_id, data_bytes)
                )

            # Vector ASC format
            elif len(parts) >= 8 and parts[3] in ("Rx", "Tx"):

                timestamp = float(parts[0])

                can_id = int(
                    parts[2]
                    .replace("x", "")
                    .replace("X", ""),
                    16
                )

                dlc = int(parts[5])

                data_bytes = bytes.fromhex(
                    " ".join(parts[6:6 + dlc])
                )

                messages.append(
                    (timestamp, can_id, data_bytes)
                )

        except Exception:
            continue

    return messages


def reduce_for_plot(df, max_points):

    if len(df) <= max_points:
        return df

    step = max(1, len(df) // max_points)

    return df.iloc[::step, :].copy()


if dbc_file and log_file:

    if st.button("Decode CAN Log"):

        with st.spinner("Decoding CAN Log..."):

            try:

                dbc_text = dbc_file.getvalue().decode(
                    "utf-8",
                    errors="ignore"
                )

                db = cantools.database.load_string(
                    dbc_text,
                    database_format="dbc"
                )

                messages = parse_can_log_fast(
                    log_file.getvalue()
                )

                decoded_rows = []

                total_messages = len(messages)
                decoded_messages = 0
                skipped_messages = 0

                for timestamp, can_id, data_bytes in messages:

                    try:

                        decoded_message = db.decode_message(
                            can_id,
                            data_bytes,
                            decode_choices=False
                        )

                        row = {
                            "Time": timestamp,
                            "CAN ID": hex(can_id)
                        }

                        row.update(decoded_message)

                        decoded_rows.append(row)

                        decoded_messages += 1

                    except Exception:
                        skipped_messages += 1

                if decoded_rows:

                    df = pd.DataFrame(decoded_rows)

                    df = (
                        df
                        .sort_values("Time")
                        .reset_index(drop=True)
                    )

                    df_analysis = (
                        df
                        .groupby("Time")
                        .first()
                        .reset_index()
                    )

                    # Memory optimization
                    for col in df_analysis.columns:

                        if col not in ["Time", "CAN ID"]:

                            df_analysis[col] = pd.to_numeric(
                                df_analysis[col],
                                errors="coerce"
                            ).astype("float32")

                    st.session_state["df_analysis"] = df_analysis

                    st.session_state["decoded_done"] = True

                    st.session_state["summary"] = {
                        "total": total_messages,
                        "decoded": decoded_messages,
                        "skipped": skipped_messages
                    }

                else:

                    st.warning(
                        "No messages decoded. "
                        "Check DBC/log compatibility."
                    )

            except Exception as e:

                st.error(f"Error: {e}")


if st.session_state.get("decoded_done"):

    df_analysis = st.session_state["df_analysis"]

    summary = st.session_state["summary"]

    st.success("Decoding completed successfully")

    st.subheader("Decoding Summary")

    col1, col2, col3 = st.columns(3)

    col1.metric(
        "Parsed Messages",
        summary["total"]
    )

    col2.metric(
        "Decoded Messages",
        summary["decoded"]
    )

    col3.metric(
        "Skipped Messages",
        summary["skipped"]
    )

    st.subheader("Data Preview")

    st.dataframe(
        df_analysis.head(int(preview_rows)),
        use_container_width=True
    )

    csv_data = df_analysis.to_csv(
        index=False
    ).encode("utf-8")

    st.download_button(
        label="Download Full Decoded CSV",
        data=csv_data,
        file_name="decoded_can_data.csv",
        mime="text/csv"
    )

    signal_columns = [
        col
        for col in df_analysis.columns
        if col not in ["Time", "CAN ID"]
    ]

    st.subheader("Signal Plot")

    selected_signals = st.multiselect(
        "Select signals to plot",
        signal_columns
    )

    plot_mode = st.radio(
        "Select plot mode",
        ["Separate Plots", "Combined Plot"]
    )

    if selected_signals:

        df_plot = df_analysis[
            ["Time"] + selected_signals
        ].copy()

        df_plot[selected_signals] = (
            df_plot[selected_signals]
            .ffill()
        )

        df_plot = reduce_for_plot(
            df_plot,
            int(max_graph_points)
        )

        st.info(
            f"Showing optimized graph with "
            f"{len(df_plot)} points."
        )

        if plot_mode == "Combined Plot":

            fig = px.line(
                df_plot,
                x="Time",
                y=selected_signals,
                render_mode="webgl",
                title="Selected CAN Signals vs Time"
            )

            fig.update_layout(
                xaxis_title="Time (s)",
                yaxis_title="Signal Value",
                legend_title="Signals"
            )

            st.plotly_chart(
                fig,
                use_container_width=True
            )

        else:

            for signal in selected_signals:

                fig = px.line(
                    df_plot,
                    x="Time",
                    y=signal,
                    render_mode="webgl",
                    title=f"{signal} vs Time"
                )

                fig.update_layout(
                    xaxis_title="Time (s)",
                    yaxis_title=signal
                )

                st.plotly_chart(
                    fig,
                    use_container_width=True
                )

else:

    st.info(
        "Upload DBC and CAN log file, "
        "then click Decode CAN Log."
    )