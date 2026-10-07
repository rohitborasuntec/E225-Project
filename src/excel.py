import os
import pandas as pd
from src.logging import logger
from datetime import datetime


class Excel:
    output_path = "Output"

    def __init__(self):

        self.date = datetime.now().strftime("%d %B %Y")
        
        hour = datetime.now().hour
        if 5 <= hour < 12:
            self.period = "Morning"
        elif 12 <= hour < 17:
            self.period = "Afternoon"
        elif 17 <= hour < 21:
            self.period = "Evening"
        else:
            self.period = "Night"
        
        os.makedirs(self.output_path, exist_ok=True)
        
        self.data = pd.DataFrame()
        
        if not os.path.exists(os.path.join(self.output_path, "g2.xlsx")):
            self.create_excel_g2()

    def create_excel_g2(self):
        columns = [
            "Date", "Time", "Link", "First product", "Second product",
            "Browser Name", "Country Name", "Version Number", "Status"
        ]
        self.data = pd.DataFrame(columns=columns)
        excel_name = os.path.join(self.output_path, "g2.xlsx")
        self.data.to_excel(excel_name, index=False)
        logger.info(f"{excel_name} has been created")

    def save_excel(self, row=None, df=None):
        file_name = os.path.join(self.output_path, "g2.xlsx")

        if row is not None:
            row["Date"] = self.date 
            row["Time"] = self.period
            columns = [
                        "Date", "Time", "Link", "First product", "Second product",
                        "Browser Name", "Country Name", "Version Number", "Status"
                    ]
            row = row[columns]
            
            if os.path.exists(file_name):
                existing = pd.read_excel(file_name)
                existing.loc[len(existing)] = row
                existing.to_excel(file_name, index=False)
            else:
                self.data.loc[len(self.data)] = row
                self.data.to_excel(file_name, index=False)

        elif df is not None:
            df.to_excel(file_name, index=False, header=True)
        logger.info(f"{file_name} has been saved")
class SponsoredResultTracker:
    """Keep a daily count of sponsored search results seen by automation."""

    columns = ["Date", "Website Name", "Seen Count", "Last Seen Time"]

    def __init__(self, output_path="Output", file_name="sponsored_results.xlsx"):
        self.output_path = output_path
        self.file_path = os.path.join(output_path, file_name)
        os.makedirs(self.output_path, exist_ok=True)

    def record_seen(self, website_name):
        website_name = " ".join(str(website_name).split()).strip()
        if not website_name:
            raise ValueError("Website name is required for sponsored-result tracking")

        now = datetime.now()
        date_value = now.strftime("%Y-%m-%d")
        time_value = now.strftime("%H:%M:%S")

        if os.path.exists(self.file_path):
            data = pd.read_excel(self.file_path, dtype=str)
            for column in self.columns:
                if column not in data.columns:
                    data[column] = ""
            data = data[self.columns]
            data["Seen Count"] = (
                pd.to_numeric(data["Seen Count"], errors="coerce")
                .fillna(0)
                .astype(int)
            )
        else:
            data = pd.DataFrame(columns=self.columns)

        names = data["Website Name"].fillna("").astype(str).str.casefold()
        dates = data["Date"].fillna("").astype(str)
        matching = (names == website_name.casefold()) & (dates == date_value)

        if matching.any():
            row_index = data.index[matching][0]
            current_count = pd.to_numeric(
                data.at[row_index, "Seen Count"], errors="coerce"
            )
            current_count = 0 if pd.isna(current_count) else int(current_count)
            new_count = current_count + 1
            data.at[row_index, "Seen Count"] = new_count
            data.at[row_index, "Last Seen Time"] = time_value
        else:
            new_count = 1
            data.loc[len(data)] = {
                "Date": date_value,
                "Website Name": website_name,
                "Seen Count": new_count,
                "Last Seen Time": time_value,
            }

        data.to_excel(self.file_path, index=False)
        logger.info(
            "Sponsored result recorded: website=%s date=%s seen_count=%s file=%s",
            website_name,
            date_value,
            new_count,
            self.file_path,
        )
        return new_count


if __name__ == "__main__":
    Excel()
