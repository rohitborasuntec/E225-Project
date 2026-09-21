import os
import pandas as pd
from src.logging import logger

class Excel:
    path = "src/excel_data"
    output_path = "output"
    def __init__(self):
        if not os.path.exists(self.path):
            self.create_excel_g2()

    def create_excel_g2(self):
        columns = [
                    "Date", "Time", "Link", "First product", "Second product",
                    "Browser Name", "Country Name", "Version Number", "Status"
                ]

        data = pd.DataFrame(columns=columns)
        data.to_excel(os.path.join(self.path, "data.xlsx"), index=False)
        logger.info("Excel has been created")

    def save_excel(self , row=None, df=None):
        file_name = "g2.xlsx"
        file_name = os.join(self.output_path,file_name)
        df.to_excel(file_name)

if __name__ == "__main__":
    
    Excel().create_excel_g2()