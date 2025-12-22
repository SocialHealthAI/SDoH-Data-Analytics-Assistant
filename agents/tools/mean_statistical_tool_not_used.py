##################################
#
#       Mean statistical tool
#       Not currently used
#
##################################

from base_statistical_tool import BaseStatisticalTool
from typing import Type, Optional
import numpy as np

class MeanStatisticalTool(BaseStatisticalTool):
    name: str = "MeanTool"
    description: str = (
        "Calculates the mean (average) of a list of numbers. "
        "Input must be a single text string in the format: 'LIST: <numbers>'. "
        "The numbers can be comma-separated, space-separated, or a JSON array. "
        "Example: 'LIST: 1, 2, 3, 4, 5' or 'LIST: [1, 2, 3, 4, 5]'. "
        "Note: The 'MATRIX:' input is ignored for this tool."
    )
    def _run(self, matrix, vector):
        """matrix: Optional array-like, vector: array-like"""
        return float(np.mean(vector))
