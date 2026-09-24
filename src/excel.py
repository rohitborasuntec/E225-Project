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


if __name__ == "__main__":
    Excel()