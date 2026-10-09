import os
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
    """Store the sponsored Google results found by the MU flow."""

    COLUMNS = [
        "Date", "Time", "Search Query", "Title", "Website Name", "Link",
        "Result Text", "TestMu Result",
    ]

    def __init__(self, output_path="Output"):
        os.makedirs(output_path, exist_ok=True)
        self.file_name = os.path.join(output_path, "sponsored_results.xlsx")
        self._ensure_workbook()

    def _ensure_workbook(self):
        """Create the MU workbook or align an existing workbook's columns."""
        if not os.path.exists(self.file_name):
            pd.DataFrame(columns=self.COLUMNS).to_excel(
                self.file_name, index=False
            )
            logger.info(f"{self.file_name} has been created")
            return

        existing = pd.read_excel(self.file_name, dtype=str)
        aligned = existing.reindex(columns=self.COLUMNS, fill_value="")
        if list(existing.columns) != self.COLUMNS:
            aligned.to_excel(self.file_name, index=False)
            logger.info(f"{self.file_name} has been updated")

    def record_result(self, result):
        """Append one complete sponsored result to the MU workbook."""
        now = datetime.now()
        row = {
            "Date": now.strftime("%Y-%m-%d"),
            "Time": now.strftime("%H:%M:%S"),
            **dict(result),
        }
        row = {column: row.get(column, "") for column in self.COLUMNS}

        if os.path.exists(self.file_name):
            existing = pd.read_excel(self.file_name, dtype=str)
            existing = existing.reindex(columns=self.COLUMNS, fill_value="")
            data = pd.concat(
                [existing, pd.DataFrame([row], columns=self.COLUMNS)],
                ignore_index=True,
            )
        else:
            data = pd.DataFrame([row], columns=self.COLUMNS)

        data.to_excel(self.file_name, index=False)
        logger.info(
            f"Sponsored result saved: website={row['Website Name']} "
            f"file={self.file_name}"
        )

    def record_seen(self, website_name):
        """Backward-compatible helper for callers that only have a domain."""
        self.record_result({"Website Name": website_name})


if __name__ == "__main__":
    Excel()
