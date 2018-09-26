import sys
import re
import logging
import numpy as np
import decimal as dec

logging.basicConfig(format="%(asctime)s - %(name)s - %(levelname)-5s - %(message)s",
                    level=logging.DEBUG,
                    datefmt='%Y-%m-%d %H:%M:%S')
logger = logging.getLogger(__name__)

try:
    None
except ImportError as exc:
    sys.stderr.write("Error: failed to import module ({})".format(exc))
    sys.stderr.write("Error: failed to import module ({})".format(exc))
    sys.exit(1)

NUMBER_AND_NAME_PATTERN = re.compile(r"^\d+\s+\D+")
DED_TYPE_PATTERN = re.compile(r"[A-Z][^:\-0-9.]*")
DED_POINT_PATTERN = re.compile(r"(?<!\d)-*\d(?:\.00|\.0)*")
DED_TOTAL_PATTERN = re.compile(r"(\d(?:\.0|\.00)*) -*\d+(?:\.0)*0*")

# TO DO - more efficient approach here
DED_ALIGNMENT_DIC = {"fall": "falls", "late start": "time violation", "illegal element": "illegal element/movement",
                     "costume violation": "costume & prop violation", "extra element by verif": "extra element",
                     "illegal element / movement": "illegal element/movement"}

EXPECTED_DED_TYPES = ["total", "falls", "time violation", "costume failure", "late start", "music violation",
                      "interruption in excess", "costume & prop violation", "illegal element/movement",
                      "extended lifts", "extra element", "illegal element", "costume violation",
                      "extra element by verif", "illegal element / movement"]


class DataRow:
    def __init__(self, raw_list=None, df=None, row=None, col_min=None):
        if df is not None and row >= 0 and col_min >= 0 and not raw_list:
            self.raw = []
            for col in range(col_min, len(df.columns)):
                if df.iloc[row, col] is not None and not is_nan(df.iloc[row, col]):
                    self.raw.append(df.iloc[row, col])
        elif raw_list:
            self.raw = raw_list
        else:
            raise ValueError(f"Please instantiate the DataRow obj with either a raw list, or a df, row and col")
        self.data = []


class ScoreRow(DataRow):
    def __init__(self, mode, raw_list=None, df=None, row=None, col_min=None):
        super().__init__(raw_list, df, row, col_min)
        logger.debug(f"Raw score list is {self.raw}")

        self.split_list = self._split_and_trim()
        self.split_index = self._get_data_start_index(mode)

    def _split_and_trim(self):
        split = []
        for c in self.raw:
            split.extend(str(c).split())
        return [r.strip() for r in split]

    def _get_data_start_index(self, mode):
        logger.debug(f"Split list is {self.split_list}")
        check_cell = 0 if mode == "pcs" else 1
        try:
            assert not is_digit_cell(self.split_list[check_cell])
        except AssertionError:
            sys.exit(f"{mode} row is fucked, content not as expected: {self.raw}")

        for i in range(check_cell, len(self.split_list)):
            if is_digit_cell(self.split_list[i]):
                return i
        sys.exit(f"Row is fucked, couldn't find any numbers in it: {self.raw}")

    def _remove_dash_columns(self, mode, row_list, judges=None, case=0, elt_list=None):
        # Context: sometimes protocols include 1-2 random columns of dashes between the end of the goe scores and the
        # total scores. But sometimes unmarked elements are also denoted by a dash. Also I hate this.
        if not judges:
            dashless = [x for x in row_list if x != "-"]
            return case, dashless[1:-1]
        else:
            logger.debug(f"Removing dashes: mode is {mode}, row is {row_list}, judges are {judges}")

            offset = 3 if mode == "goe" else 2

            test = [x for x in row_list if x != "-"]
            if case == 1 or len(test) == (offset + judges):
                case = 1
                return case, test

            test_2 = ["NS" if x == "-" else x for x in row_list]
            if case == 2 or len(test_2) == (offset + judges):
                case = 2
                return case, test_2
            elif case == 3 or ((len(test_2) - offset - judges) == 1 and test_2[-2] == "NS"):
                del test_2[-2]
                case = 3
                return case, test_2
            elif case == 4 or ((len(test_2) - offset - judges) == 2 and test_2[-3:-1] == ["NS", "NS"]):
                del test_2[-3:-1]
                case = 4
                return case, test_2
            elif case == 5 or ((len(test_2) - offset - judges) == 3 and test_2[-4:-1] == ["NS", "NS", "NS"]):
                del test_2[-4:-1]
                case = 5
                return case, test_2
            elif elt_list and len(elt_list) > 0:
                return self._infer_from_previous_element(mode, row_list, judges, elt_list)
            sys.exit(f"Elt row does not have expected length: {self.raw}, {row_list}")

    def _infer_from_previous_element(self, mode, row_list, judges, elt_list):
        case, dashless = self._remove_dash_columns(mode=mode, row_list=row_list, judges=judges, case=elt_list[-1].case)
        return case, dashless


class PCSRow(ScoreRow):
    def __init__(self, elt_list=None, judges=None, raw_list=None, df=None, row=None, col_min=None):
        super().__init__(mode="pcs", raw_list=raw_list, df=df, row=row, col_min=col_min)
        self.id = None
        self.row_label = " ".join(self.split_list[0:self.split_index])
        self.case, self.data = self._clean_pcs_row(judges, elt_list)

    def _clean_pcs_row(self, judges, elt_list):
        case, scores = self._remove_dash_columns(mode="pcs", judges=judges, row_list=self.split_list[self.split_index:], elt_list=elt_list)
        clean = coerce_to_num_type(list_=[r.replace(",", ".") for r in scores], target_type="decimal")
        logger.debug(f"Cleaned scores list is {clean}")
        return case, clean


class GOERow(ScoreRow):
    def __init__(self, elt_list, judges, raw_list=None, df=None, row=None, col_min=None):
        super().__init__(mode="goe", raw_list=raw_list, df=df, row=row, col_min=col_min)

        self.row_no = int(self.split_list[0])
        self.row_label = " ".join(self.split_list[1:self.split_index])
        self.case, self.data = self._clean_goe_row(judges, elt_list)

    def _clean_goe_row(self, judges, elt_list):
        temp = self.split_list[self.split_index:]
        if "x" in temp:
            self.row_label += " x"
            temp.remove("x")
        elif "X" in temp:
            self.row_label += " x"
            temp.remove("X")

        case, dashless = self._remove_dash_columns(mode="goe", judges=judges, row_list=temp, elt_list=elt_list)
        scores = [r.replace(",", ".") for r in dashless]
        logger.debug(f"After removing dashes scores are {scores}")

        one = coerce_to_num_type(list_=scores[0:2], target_type="decimal")
        two = coerce_to_num_type(list_=scores[2:-1], target_type="int")
        three = coerce_to_num_type(list_=[scores[-1]], target_type="decimal")
        return case, one + two + three


class NameRow(DataRow):
    def __init__(self, mode, raw=None, df=None, row=None, col_min=None):
        super().__init__(raw, df, row, col_min)
        self.clean_name_row(mode)

    def clean_name_row(self, mode):
        if mode == "single line":
            self.data = self.raw
        elif mode == "multiline":
            self.data = [c.rpartition("\n")[2] for c in self.raw]
        else:
            raise ValueError("Mode parameter must be set to either 'single line' or 'multiline'")
        if re.search(NUMBER_AND_NAME_PATTERN, str(self.data[0])):
            split_cell = str(self.data[0]).split(" ", 1)
            self.data[0] = int(split_cell[0])
            self.data.insert(1, split_cell[1])


class DeductionRow(DataRow):
    def __init__(self, raw=None, df=None, row=None, col_min=None):
        super().__init__(raw, df, row, col_min)
        self.ded_detail = self.parse_deduction_dictionary()

    def _split_on_colon(self):
        split_row = []
        for c in self.raw:
            if ": " in str(c) and str(c).split(": ")[1] != "":
                split_row.extend([e for e in str(c).split(": ")])
            else:
                split_row.append(str(c))
        return split_row

    def _split_on_newline(self, input_row):
        output_row, i = [], 0
        while i < len(input_row):
            if "\n" in str(input_row[i]):
                # If find newline in text cell: is neighbouring cell a digit cell? if so, handle both, zip and increment
                # by two. If not, handle this cell only.
                this_cell = str(input_row[i]).split("\n")

                if is_text_cell(input_row[i]) and i + 1 < len(input_row) and is_digit_cell(input_row[i + 1]):
                    logger.debug(f"For cell {input_row[i]} we are in case 1: newline")
                    next_cell = str(input_row[i + 1]).split("\n")
                    if len(this_cell) != len(next_cell):
                        for i in range(0, max(len(this_cell), len(next_cell))):
                            try:
                                if not is_ded_type_string(this_cell[i]):
                                    del this_cell[i]
                            except IndexError:
                                pass
                            try:
                                if not is_int(next_cell[i]):
                                    del next_cell[i]
                            except IndexError:
                                pass
                    try:
                        assert len(this_cell) == len(next_cell)
                    except AssertionError:
                        sys.exit(f"Ya deductions cells still don't match girl, {this_cell} vs. {next_cell}")

                    output_row.extend([item for pair in zip(this_cell, next_cell) for item in pair])
                    i += 2
                else:
                    logger.debug(f"this cell is {this_cell}")
                    filtered_list = [i for i in this_cell if is_digit_cell(i) and is_int(i) or
                                     is_text_cell(i) and is_ded_type_string(i)]
                    logger.debug(f"Filtered list is {filtered_list}")
                    output_row.extend(filtered_list)
                    i += 1
            elif not is_ded_type_string(input_row[i]):
                i += 1
            else:
                output_row.append(str(input_row[i]))
                i += 1
        return output_row

    def parse_deduction_dictionary(self):
        logger.debug(f"Raw deductions list is {self.raw}")

        split_row_1 = self._split_on_colon()
        logger.debug(f"Row after first split is {split_row_1}")

        split_row_2 = self._split_on_newline(split_row_1)
        logger.debug(f"Row text after second split is {split_row_2}")

        row_less_falls = [re.sub(r"\(\d+\)", "", str(r)) for r in split_row_2]
        logger.debug(f"Row text after score removal is  is {row_less_falls}")
        row_text = " ".join(row_less_falls)
        logger.debug(f"Row text after join is {row_text}")

        row_text = re.sub(DED_TOTAL_PATTERN, r"\1", row_text)
        logger.debug(f"Row text after total removal is {row_text}")

        ded_words = re.findall(DED_TYPE_PATTERN, row_text)
        ded_digits = re.findall(DED_POINT_PATTERN, row_text)

        logger.debug(f"ded words and digits after regex {ded_words}, {ded_digits}")

        # Clean up ded types
        ded_words = [DED_ALIGNMENT_DIC[d.lower().strip()] if d.lower().strip() in DED_ALIGNMENT_DIC
                     else d.lower().strip() for d in ded_words]
        for d in ded_words:
            if d == 'total':
                del d
            elif d not in EXPECTED_DED_TYPES:
                sys.exit(f"Detected unexpected deduction: {d}")

        # Remove other random numbers that might have ended up in the row, ensure all numbers negative
        ded_digits = [x for x in ded_digits if x is not None]
        ded_digits = [-1 * int(float(x)) if int(float(x)) > 0 else int(float(x)) for x in ded_digits]

        if len(ded_words) != len(ded_digits):
            sys.exit(f"Lol ya deductions lists are fucked girl: {ded_words} vs. {ded_digits}")

        ded_dic_raw = dict(zip(ded_words, ded_digits))
        ded_dic = {k: v for k, v in ded_dic_raw.items() if int(v) != 0}
        logger.debug(f"Returning deductions dic: {ded_dic})")
        return ded_dic


def is_text_cell(x):
    return True if re.match(r"^[A-Za-z\- \n:]+$", x) else False


def is_digit_cell(x):
    return True if re.match(r"^[\d., \n]+$", x) else False


def is_nan(x):
    return x is np.nan or x != x


def is_int(x):
    return True if re.search(r"^-?\d{1,2}(\.0|\.00)?(?!\.[1-9]{1,2})$", x) else False


def is_ded_type_string(x):
    return True if "deductions" not in str(x).lower() and "score" not in str(x).lower() else False


def coerce_to_num_type(list_, target_type):
    coerced_list = []
    for c in list_:
        if target_type == "decimal":
            try:
                coerced_list.append(dec.Decimal(str(c)))
            except (dec.InvalidOperation, ValueError):
                pass
        elif target_type == "float":
            try:
                coerced_list.append(float(c))
            except ValueError:
                pass
        elif target_type == "int":
            try:
                coerced_list.append(int(float(c)))
            except ValueError:
                pass
        else:
            raise ValueError("Please set 'mode' parameter to 'float' or 'int'")
    logger.debug(f"Coerced list is {coerced_list}")
    return coerced_list