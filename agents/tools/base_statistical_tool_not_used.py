##################################
#
#       Base Class for statistical tools accepting matrix input.
#       Not currently used
#
##################################

from langchain.tools import BaseTool
from pydantic import BaseModel, Field
from typing import Type, Optional
from abc import ABC, abstractmethod
import numpy as np
import json
import re


class StatisticalToolInput(BaseModel):
    matrix: Optional[str] = Field(None, description="Matrix input as JSON string or CSV rows.")
    list_: str = Field(..., description="List/vector input as JSON, CSV, or space-separated string.")


class BaseStatisticalTool(BaseTool, ABC):
    name: str = "BaseStatisticalTool"
    description: str = "Base class for statistical tools."

    @abstractmethod
    #def _run(self, matrix: Optional[np.ndarray], vector: np.ndarray) -> float:
    def _run(self, matrix, vector):
        """matrix: Optional array-like, vector: array-like"""
        pass

    def parse_list(self, text: str) -> np.ndarray:
        try:
            return np.array(json.loads(text))
        except json.JSONDecodeError:
            return np.array([float(x) for x in text.replace(",", " ").split()])

    def parse_matrix(self, text: Optional[str]) -> Optional[np.ndarray]:
        if text is None:
            return None
        try:
            return np.array(json.loads(text))
        except json.JSONDecodeError:
            rows = text.strip().split("\n")
            return np.array([[float(x) for x in row.replace(",", " ").split()] for row in rows])

    def validate_inputs(self, matrix: Optional[np.ndarray], vector: np.ndarray):
        if vector is None:
            raise ValueError("List/vector input is required.")
        if matrix is not None and not isinstance(matrix, np.ndarray):
            raise TypeError("Matrix must be a NumPy array.")
        if not isinstance(vector, np.ndarray):
            raise TypeError("Vector must be a NumPy array.")

    def _run_tool(self, matrix: Optional[str], list_: str) -> float:
        vector = self.parse_list(list_)
        matrix_array = self.parse_matrix(matrix)
        self.validate_inputs(matrix_array, vector)
        return self._run(matrix_array, vector)

    def run(self, input: str) -> str:
        # Single text input: must parse matrix/list_ from it
        matrix, list_ = self.parse_single_input(input)
        result = self._run_tool(matrix, list_)
        return f"Result: {result}"

    async def arun(self, input: str) -> str:
        return self.run(input)

    def parse_single_input(self, input: str) -> tuple[Optional[str], str]:
        """
        Naive example:
          - If input contains 'MATRIX:' and 'LIST:'
          - Or use regex or other structured pattern.
        """
        matrix = None
        list_ = None

        matrix_match = re.search(r"MATRIX:(.*?)LIST:", input, re.DOTALL | re.IGNORECASE)
        list_match = re.search(r"LIST:(.*)", input, re.DOTALL | re.IGNORECASE)

        if matrix_match:
            matrix = matrix_match.group(1).strip()

        if list_match:
            list_ = list_match.group(1).strip()
        else:
            list_ = input.strip()  # fallback: assume whole input is the list

        if not list_:
            raise ValueError("Could not parse 'LIST:' from input.")
        return matrix, list_
