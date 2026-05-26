import streamlit as st
import pandas as pd
import cantools
import plotly.express as px

st.set_page_config(page_title="CAN Log Interpreter", layout="wide")

st.title("CAN Log Interpreter")
st.write("Supports BUSMASTER .log/.txt/.asc and DBC based CAN signal decoding.")

dbc_file = st.file_uploader("Upload DBC File", type=["dbc"])

log_file = st.file_uploader(
    "Upload CAN Log File",
    type=["log", "txt", "asc"]
)


def parse_can_log(file_content):
    messages = []

    lines = file_content.decode("utf-8", errors="ignore").splitlines()

    for line in lines:
        line = line.strip()

        if not line or line.startswith("***"):
            continue

        parts = line.split()

        try:
            # BUSMASTER format:
            # 17:24:35:1107 Rx 1 0x109 s 8 59 02 74 02 DE 3E 00 00
            if len(parts) >= 7 and parts[1] in ["Rx", "Tx"]:

                time_str = parts[0]
                can_id = int(parts[3], 16)
                dlc = int(parts[5])
                data_bytes = bytes(int(x, 16) for x in parts[6:6 + dlc])

                h, m, s, ms = time_str.split(":")
                timestamp = (
                    int(h) * 3600 +
                    int(m) * 60 +
                    int(s) +
                    int(ms) / 10000
                )

                messages.append({
                    "Time": timestamp,
                    "CAN ID": can_id,
                    "Data": data_bytes
                })

            # Vector ASC format:
            # 0.123456 1 109 Rx d 8 59 02 74 02 DE 3E 00 00
            elif len(parts) >= 7 and parts[3] in ["Rx", "Tx"]:

                timestamp = float(parts[0])
                can_id_text = parts[2].replace("x", "")
                can_id = int(can_id_text, 16)
                dlc = int(parts[5])
                data_bytes = bytes(int(x, 16) for x in parts[6:6 + dlc])

                messages.append({
                    "Time": timestamp,
                    "CAN ID": can_id,
                    "Data": data_bytes
                })

        except Exception:
            continue

    return messages


if dbc_file and log_file:

    st.success("Files uploaded successfully")

    try:
        # Load DBC directly from memory
        dbc_text = dbc_file.getvalue().decode("utf-8", errors="ignore")
        db = cantools.database.load_string(dbc_text, database_format="dbc")

        # Read log directly from memory
        log_content = log_file.getvalue()
        messages = parse_can_log(log_content)

        decoded_rows = []
        total_messages = len(messages)
        decoded_messages = 0
        skipped_messages = 0

        for msg in messages:
            try:
                decoded_message = db.decode_message(
                    msg["CAN ID"],
                    msg["Data"],
                    decode_choices=False
                )

                row = {
                    "Time": msg["Time"],
                    "CAN ID": hex(msg["CAN ID"])
                }

                for signal_name, signal_value in decoded_message.items():
                    row[signal_name] = signal_value

                decoded_rows.append(row)
                decoded_messages += 1

            except Exception:
                skipped_messages += 1

        if decoded_rows:

            df = pd.DataFrame(decoded_rows)
            df = df.sort_values("Time").reset_index(drop=True)

            signal_columns = [
                col for col in df.columns
                if col not in ["Time", "CAN ID"]
            ]

            df_analysis = df.groupby("Time").first().reset_index()

            df_plot = df_analysis.copy()
            df_plot[signal_columns] = df_plot[signal_columns].ffill()

            st.subheader("Decoding Summary")

            col1, col2, col3 = st.columns(3)
            col1.metric("Total Messages in Log", total_messages)
            col2.metric("Decoded Messages", decoded_messages)
            col3.metric("Skipped Messages", skipped_messages)

            st.subheader("Decoded CAN Data")
            st.dataframe(df_analysis, use_container_width=True)

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

                if plot_mode == "Combined Plot":
                    fig = px.line(
                        df_plot,
                        x="Time",
                        y=selected_signals,
                        title="Selected CAN Signals vs Time"
                    )

                    fig.update_layout(
                        xaxis_title="Time (s)",
                        yaxis_title="Signal Value",
                        legend_title="Signals"
                    )

                    st.plotly_chart(fig, use_container_width=True)

                else:
                    for signal in selected_signals:
                        fig = px.line(
                            df_plot,
                            x="Time",
                            y=signal,
                            title=f"{signal} vs Time"
                        )

                        fig.update_layout(
                            xaxis_title="Time (s)",
                            yaxis_title=signal
                        )

                        st.plotly_chart(fig, use_container_width=True)

            else:
                st.info("Select one or more signals to plot.")

            csv_data = df_analysis.to_csv(index=False).encode("utf-8")

            st.download_button(
                label="Download Decoded CSV",
                data=csv_data,
                file_name="decoded_can_data.csv",
                mime="text/csv"
            )

        else:
            st.warning(
                "No messages decoded. Possible reasons: CAN ID mismatch, DBC mismatch, "
                "or unsupported log format."
            )

    except Exception as e:
        st.error(f"Error: {e}")

else:
    st.info("Please upload both DBC file and CAN log file.")