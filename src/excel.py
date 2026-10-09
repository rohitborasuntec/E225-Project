import os
import csv
import pandas as pd
from datetime import datetime
from src.logging import logger


class Excel:
    output_path = "Output"
    COLUMNS = [
        "Date", "Time", "Link", "First product", "Second product",
        "Browser Name", "Country Name", "Version Number", "Status",
    ]

    def __init__(self):
        now = datetime.now()
        self.date = now.strftime("%d %B %Y")
        hour = now.hour
        if 5 <= hour < 12:
            self.period = "Morning"
        elif 12 <= hour < 17:
            self.period = "Afternoon"
        elif 16 <= hour < 21:
            self.period = "Evening"
        else:
            self.period = "Night"

        os.makedirs(self.output_path, exist_ok=True)
        self.file_name = os.path.join(self.output_path, "g2.xlsx")

        if not os.path.exists(self.file_name):
            self._create()

    def _create(self):
        pd.DataFrame(columns=self.COLUMNS).to_excel(self.file_name, index=False)
        logger.info(f"{self.file_name} has been created")

    def check_if_completed(self, product, comparing_product):
        if not os.path.exists(self.file_name):
            return False

        existing = pd.read_excel(self.file_name)

        completed_data = existing[(existing["Date"] == self.date) & (existing["Time"] == self.period) & (existing["Status"] == "Done") & (existing["First product"] == product) & (existing["Second product"] == comparing_product)]

        if completed_data.empty:
            return False

        return True

        
    def save_excel(self, row=None, df=None):
        if row is not None:
            row = dict(row)
            row["Date"] = self.date
            row["Time"] = self.period
            row = {col: row.get(col, "") for col in self.COLUMNS}

            if os.path.exists(self.file_name):
                existing = pd.read_excel(self.file_name)
                # FIX: align columns (pd.concat with a dict can misalign if the
                # existing file has extra/missing columns).
                existing = existing.reindex(columns=self.COLUMNS)
                combined = pd.concat(
                    [existing, pd.DataFrame([row], columns=self.COLUMNS)],
                    ignore_index=True,
                )
                combined.to_excel(self.file_name, index=False)
            else:
                pd.DataFrame([row], columns=self.COLUMNS).to_excel(
                    self.file_name, index=False,
                )
        elif df is not None:
            df.to_excel(self.file_name, index=False, header=True)

        logger.info(f"{self.file_name} has been saved")


class SponsoredResultTracker:
    """Track sponsored websites in an Ads Clicked Tracker CSV matrix."""

    CSV_NAME = "TestMu Ads Clicked Tracker.csv"
    RUN_LOG_NAME = "TestMu Run Log.csv"

    def __init__(self, output_path="Output"):
        os.makedirs(output_path, exist_ok=True)
        self.file_name = os.path.join(output_path, self.CSV_NAME)
        self.csv_file_name = os.path.join(output_path, self.RUN_LOG_NAME)
        self._ensure_tracker_csv()
        self._ensure_run_log_csv()

    def _ensure_run_log_csv(self):
        if os.path.exists(self.csv_file_name):
            return
        with open(self.csv_file_name, "w", newline="", encoding="utf-8") as file:
            csv.writer(file).writerow(["Timestamp", "Step", "Status", "Details"])
        logger.info(f"{self.csv_file_name} has been created")

    def log_event(self, step, status="ok", details=""):
        with open(self.csv_file_name, "a", newline="", encoding="utf-8") as file:
            csv.writer(file).writerow([
                datetime.now().isoformat(timespec="seconds"),
                step,
                status,
                details,
            ])

    def _ensure_tracker_csv(self):
        """Create/normalize the date-column tracker CSV."""
        if not os.path.exists(self.file_name):
            with open(self.file_name, "w", newline="", encoding="utf-8") as file:
                csv.writer(file).writerows([
                    ["", "Sum ->"],
                    ["", "Company / Date"],
                ])
            logger.info(f"{self.file_name} has been created")

        with open(self.file_name, newline="", encoding="utf-8") as file:
            rows = list(csv.reader(file))
        if not rows or rows[0][:1] == ["Timestamp"]:
            rows = [["", "Sum ->"], ["", "Company / Date"]]
        while len(rows) < 2:
            rows.append([])
        rows[0] = rows[0] + [""] * (max(0, len(rows[1]) - len(rows[0])))
        rows[1] = rows[1] + [""] * (len(rows[0]) - len(rows[1]))
        with open(self.file_name, "w", newline="", encoding="utf-8") as file:
            csv.writer(file).writerows(rows)
        self._ensure_today_column()

    def _ensure_today_column(self):
        today = datetime.now().strftime("%d-%m-%Y")
        with open(self.file_name, newline="", encoding="utf-8") as file:
            rows = list(csv.reader(file))
        date_column = None
        for column in range(2, len(rows[1])):
            if rows[1][column] == today:
                date_column = column
                break
        if date_column is None:
            date_column = max(2, len(rows[1]))
            for row in rows:
                row.extend([""] * (date_column + 1 - len(row)))
            rows[1][date_column] = today
            logger.info(f"Added Ads Clicked Tracker date column: {today}")
        self._write_tracker_rows(rows, date_column)
        self.today_column = date_column

    def _write_tracker_rows(self, rows, date_column):
        width = max(len(row) for row in rows)
        for row in rows:
            row.extend([""] * (width - len(row)))
        total = 0
        for row in rows[2:]:
            try:
                total += int(float(row[date_column] or 0))
            except (ValueError, IndexError):
                row[date_column] = ""
        rows[0][date_column] = str(total)
        with open(self.file_name, "w", newline="", encoding="utf-8") as file:
            csv.writer(file).writerows(rows)

    def record_result(self, result):
        """Increment the website count under today's date column."""
        website = " ".join(str(result.get("Website Name", "")).split()).strip()
        if not website:
            return
        with open(self.file_name, newline="", encoding="utf-8") as file:
            rows = list(csv.reader(file))
        website_row = None
        for row_index in range(2, len(rows)):
            value = rows[row_index][1] if len(rows[row_index]) > 1 else ""
            if str(value or "").strip().casefold() == website.casefold():
                website_row = row_index
                break
        if website_row is None:
            website_row = len(rows)
            rows.append([""] * max(self.today_column + 1, 2))
            rows[website_row][1] = website
        for row in rows:
            row.extend([""] * (self.today_column + 1 - len(row)))
        current = float(rows[website_row][self.today_column] or 0)
        rows[website_row][self.today_column] = str(int(current + 1))
        self._write_tracker_rows(rows, self.today_column)
        logger.info(
            f"Sponsored result count incremented: website={website} "
            f"date={datetime.now().date()} file={self.file_name}"
        )

    def record_seen(self, website_name):
        """Backward-compatible helper for callers that only have a domain."""
        self.record_result({"Website Name": website_name})


if __name__ == "__main__":
    Excel()
