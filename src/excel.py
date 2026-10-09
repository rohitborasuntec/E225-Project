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
    
    def browser_list(self):
        if not os.path.exists(self.file_name):
            return []

        existing = pd.read_excel(self.file_name)

        completed_data = existing[(existing["Date"] == self.date) & (existing["Time"] == self.period) & (existing["Status"] == "Done")]
        
        if completed_data.empty:
            return []

        return completed_data["Browser Name"].unique().tolist()
        
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


if __name__ == "__main__":
    Excel()