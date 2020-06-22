# Evaluate the recognized dataset against the ideal dataset.
# Usage: evaluation.py ideal recognized
# (ideal & recognized are directories)

# Imports
import argparse
from pathlib import Path
from typing import Dict, Tuple
import re
import Levenshtein.StringMatcher as levenshtein
import progressbar
import csv
import codecs

# Type Definitions
Line = Dict[str, str]
Result = Dict[str, str]

# Evaluation
def main() -> None:
    parser = argparse.ArgumentParser(description='Evaluate the recognized dataset against the ideal dataset.')
    # Ideal Directory
    parser.add_argument('ideal', metavar='ideal', type=str, nargs=1, help='a directories containing the ideal dataset')
    # Recognized Directory
    parser.add_argument('recognized', metavar='recognized', type=str, nargs=1, help='a directories containing the recognized dataset')
    # Output Directory
    parser.add_argument('-o', metavar='output', type=str, nargs=1, help='A path where the results can be saved.')
    # How many percent of the ground truth box should be in the accepted box? (Default ist 1)
    parser.add_argument('-cp', metavar='coordinate_percent', type=float, nargs=1, default=1.0, help='how many percent of the ground truth box should be in the accepted box? (Default ist 1.0)')
    # Accepted Levenshtein Distance
    parser.add_argument('-lp', metavar='levenshtein_percent', type=float, nargs=1, default=1.0, help='how off can the determination be? (Default is 1.0)')
    args = parser.parse_args()

    coordinate_percent: float = args.cp[0] if isinstance(args.cp, list) else args.cp
    levenshtein_percent: float = args.lp[0] if isinstance(args.lp, list) else args.lp
    evaluate(Path(args.ideal[0]).absolute(), Path(args.recognized[0]).absolute(), Path(args.o[0]).absolute(), coordinate_percent, levenshtein_percent)


def evaluate(ideal_path, recognized_path, outpath, coordinate_percent, levenshtein_percent):
    # INPUT FEEDBACK
    outpath.mkdir(parents=True, exist_ok=True)

    # Input
    print('\n')
    print('CONFIG:')
    print('ideal_path:\t\t' + str(ideal_path))
    print('recognized_path:\t' + str(recognized_path))

    # Configuation
    print('Coordinate Percent:\t' + str(coordinate_percent))
    print('Levenshtein Percent:\t' + str(levenshtein_percent))
    print('\n')

    ideal_files: [Path] = []
    for path in Path(ideal_path).rglob('*.txt'):
        ideal_files.append(path.absolute())

    first_ideal: bool = True
    first_recognized: bool = True

    # Values
    overall_TP_l: int = 0    # True Positives   (ideal coordinate in recognized coordinates)
    overall_FP_l: int = 0    # False Positives  (recognized coordinate not in ideal coordinates)
    overall_FN_l: int = 0    # False Negatives  (ideal coordinate not in recognized coordinates)
    overall_TP_d: int = 0    # True Positives   (ideal word in recognized words [in same coordinates])
    overall_FP_d: int = 0    # False Positives  (recognized word not in ideal words)
    overall_FN_d: int = 0    # False Negatives  (ideal word not in recognized words [in same coordinates])

    file_results: [Result] = [{'path': '', 'tp_l': '', 'fp_l': '', 'fn_l': '', 'tp_d': '', 'fp_d': '', 'fn_d': '', 'time_l': '', 'time_d': '', 'time_c': ''}] 

    # EVALUATE THE FILES
    for i in progressbar.progressbar(range(len(ideal_files))):
        ideal_file_path = ideal_files[i]
        recognized_file_path: str = str(get_recognized(ideal_file_path, ideal_path, recognized_path))
        
        # RETRIEVE THE DATA
        ideal: Line = [{'word': '', 'left': '', 'top': '', 'width': '', 'height': ''}]
        recognized: Line = [{'word': '', 'left': '', 'top': '', 'width': '', 'height': ''}]

        time_l: int = 0
        time_d: int = 0

        with open(str(ideal_file_path), 'r') as f:
            # print('load:\t' + str(ideal_file_path))
            for line in f:
                # print(line)
                if len(line) <= 1 or 'file:///' in line:
                    continue
                if '% Time' in line:
                    time_l += get_time(line)
                else:
                    ideal.append(get_word_coordinate_dict(line))
                    if first_ideal:
                        first_ideal = False
        with open(recognized_file_path, 'r') as f:
            # print('load:\t' + recognized_file_path)
            for line in f:
                if len(line) <= 1 or 'file:///' in line:
                    continue
                if '% Time' in line:
                    time_d += get_time(line)
                else:
                    recognized.append(get_word_coordinate_dict(line))
                    if first_recognized:
                        first_recognized = False

        del ideal[0]
        del recognized[0]
        # EVALUATE THE DATA
        file_result: Result = {'path': recognized_file_path, 'tp_l': '', 'fp_l': '', 'fn_l': '', 'tp_d': '', 'fp_d': '', 'fn_d': ''} 

        # LOCALISATION
        TP_l: int = 0    # True Positives   (ideal coordinate in recognized coordinates)
        FP_l: int = 0    # False Positives  (recognized coordinate not in ideal coordinates)
        FN_l: int = 0    # False Negatives  (ideal coordinate not in recognized coordinates)
        recognized_copy = recognized.copy()
        for ideal_line in ideal:
            found: bool = False
            for i in range(len(recognized_copy)):
                if validate_coordinate(ideal_line, recognized_copy[i], coordinate_percent):
                    found = True
                    del recognized_copy[i]
                    break
            if found:
                TP_l += 1
            else:
                FN_l += 1
            found = False
        FP_l = len(recognized) - TP_l # FP = Pr - TP (Pr are the overall localized)

        # print('\nideal_len: ' + str(len(ideal)))
        # print('\nideal: ' + str(ideal))
        # print('recognized_len: ' + str(len(recognized)))
        # print('recognized: ' + str(recognized))
        # print('TP_l: ' + str(TP_l))
        # print('FP_l: ' + str(FP_l))

        # save the values
        file_result['tp_l'] = str(TP_l)
        file_result['fp_l'] = str(FP_l)
        file_result['fn_l'] = str(FN_l)
        overall_TP_l += TP_l
        overall_FP_l += FP_l
        overall_FN_l += FN_l

        # DETERMINATION
        # maybe change localisation in a way that we only have the lines where the coordinates are correct
        # not good because if word is recognized correctly but coordinates too off? (Can this happen?)
        # how to handle ''\t(12,213,34,54) cases? Will they appear? Maybe add new count? they are in FP_d right now
        TP_d: int = 0    # True Positives   (ideal word in recognized words [in same coordinates])
        FP_d: int = 0    # False Positives  (recognized word not in ideal words)
        FN_d: int = 0    # False Negatives  (ideal word not in recognized words [in same coordinates])
        recognized_copy = recognized.copy()
        for ideal_line in ideal:
            found: bool = False
            for i in range(len(recognized_copy)):
                if validate_word(ideal_line, recognized_copy[i], coordinate_percent, levenshtein_percent):
                    found = True
                    del recognized_copy[i]
                    break
            if found:
                TP_d += 1
            else:
                FN_d += 1
            found = False
        FP_d = len(recognized) - TP_d # FP = Pr - TP (Pr are the overall determined)

        # save the values
        file_result['tp_d'] = str(TP_d)
        file_result['fp_d'] = str(FP_d)
        file_result['fn_d'] = str(FN_d)
        file_result['time_l'] = str(time_l)
        file_result['time_d'] = str(time_d)
        file_result['time_c'] = str(time_l + time_d)
        overall_TP_d += TP_d
        overall_FP_d += FP_d
        overall_FN_d += FN_d

        file_results.append(file_result)

    # Remove first empty result
    if len(file_results) > 1:
        del file_results[0]

    # Further Evaluation
    # LOCALISATION
    accuracy_l: float = -1.0
    precision_l: float = -1.0
    recall_l: float = -1.0
    fone_score_l: float = -1.0
    try:
        accuracy_l = (overall_TP_l) / (overall_TP_l + overall_FP_l + overall_FN_l)
    except:
        pass
    try:
        precision_l = (overall_TP_l) / (overall_TP_l + overall_FP_l)
    except:
        pass
    try:
        recall_l = (overall_TP_l) / (overall_TP_l + overall_FN_l)
    except:
        pass
    try:
        fone_score_l =  2 * (precision_l * recall_l) / (precision_l + recall_l)
    except:
        pass

    # DETERMINATION
    accuracy_d: float = -1.0
    precision_d: float = -1.0
    recall_d: float = -1.0
    fone_score_d: float = -1.0
    try:
        accuracy_d = (overall_TP_d) / (overall_TP_d + overall_FP_d + overall_FN_d)
    except:
        pass
    try:
        precision_d = (overall_TP_d) / (overall_TP_d + overall_FP_d)
    except:
        pass
    try:
        recall_d = (overall_TP_d) / (overall_TP_d + overall_FN_d)
    except:
        pass
    try:
        fone_score_d =  2 * (precision_d * recall_d) / (precision_d + recall_d)
    except:
        pass

    # Input
    log: str = ''
    log += 'ideal_path:\t\t' + str(ideal_path) + '\n'
    log += 'recognized_path:\t' + str(recognized_path) + '\n'

    # Configuation
    log += '\n'
    
    log += 'Coordinate Percent:\t' + str(coordinate_percent) + '\n'
    log += 'Levenshtein Percent:\t' + str(levenshtein_percent) + '\n'
    # Localisation Results
    log += '\n'
    log += 'LOCALISATION:' + '\n'
    log += 'TP_l:\t\t' + str(overall_TP_l) + '\n'
    log += 'FP_l:\t\t' + str(overall_FP_l) + '\n'
    log += 'FN_l:\t\t' + str(overall_FN_l) + '\n'
    log += '(' + 'accuracy_l:\t' + str(accuracy_l) + ')' + '\n'
    log += 'precision_l:\t' + str(precision_l) + '\n'
    log += 'recall_l:\t' + str(recall_l) + '\n'
    log += 'fone_score_l:\t' + str(fone_score_l) + '\n'


    # Determination Results
    log += '\n'
    log += 'DETERMINATION:' + '\n'
    log += 'TP_d:\t\t' + str(overall_TP_d) + '\n'
    log += 'FP_d:\t\t' + str(overall_FP_d) + '\n'
    log += 'FN_d:\t\t' + str(overall_FN_d) + '\n'
    log += '(' + 'accuracy_d:\t' + str(accuracy_d) + ')' + '\n'
    log += 'precision_d:\t' + str(precision_d) + '\n'
    log += 'recall_d:\t' + str(recall_d) + '\n'
    log += 'fone_score_d:\t' + str(fone_score_d) + '\n'

    print('\n' + log)

    # Save the evaluation results
    log_filename: str = str(outpath.joinpath('evaluation_' + ideal_path.name + '_' + recognized_path.name + '_cp' + str(coordinate_percent).replace('.', '') + '_lp' + str(levenshtein_percent).replace('.', '') + '.txt'))
    with codecs.open(log_filename, 'w', "utf-8-sig") as f:
        f.write(log)
    print('\ncreated:\t' + log_filename)

    csv_filename: str = str(outpath.joinpath('evaluation_' + ideal_path.name + '_' + recognized_path.name + '_cp' + str(coordinate_percent).replace('.', '') + '_lp' + str(levenshtein_percent).replace('.', '') + '.csv'))
    csv_keys = file_results[0].keys()
    with codecs.open(csv_filename, 'w', "utf-8-sig") as f:
        dict_writer = csv.DictWriter(f, csv_keys)
        dict_writer.writeheader()
        dict_writer.writerows(file_results)
    print('created:\t' + csv_filename)

def get_recognized(file_path: Path, ideal_path: Path, recognized_path: Path) -> Path:
    return Path(str(file_path).replace(str(ideal_path),str(recognized_path)))

def get_word_coordinate_dict(line: str) -> Line:
    output: Line = {'word': '', 'left': '', 'top': '', 'width': '', 'height': ''}

    splitted_line = line.split('\t')
    try:
        output['word'] = normalize_word(splitted_line[0])
        coordinates = re.search(r'(\d+),(\d+),(\d+),(\d+)', splitted_line[1]).groups()
        output['left'] = coordinates[0]
        output['top'] = coordinates[1]
        output['width'] = coordinates[2]
        output['height'] = coordinates[3]
    except:
        pass

    return output

def get_time(line: str) -> int:
    return int(re.search(r'\d+', line)[0])

def validate_coordinate(ideal_line: Line, recognized_line: Line, coordinate_percent: float) -> bool:
    valid_input: bool = (
            ideal_line['left'] and
            ideal_line['top'] and
            ideal_line['width'] and
            ideal_line['height'] and
            recognized_line['left'] != '' and
            recognized_line['top'] != '' and
            recognized_line['width'] != '' and
            recognized_line['height'] != ''
        )

    if not valid_input:
        return False

    valid_box: bool = False

    ideal_x_min: int = int(ideal_line['left'])
    ideal_y_min: int = int(ideal_line['top'])
    ideal_x_max: int = int(ideal_line['left']) + int(ideal_line['width'])
    ideal_y_max: int = int(ideal_line['top']) + int(ideal_line['height'])
    recognized_x_min: int = int(recognized_line['left'])
    recognized_y_min: int = int(recognized_line['top'])
    recognized_x_max: int = int(recognized_line['left']) + int(recognized_line['width'])
    recognized_y_max: int = int(recognized_line['top']) + int(recognized_line['height'])

    ideal_area: float = int(ideal_line['width']) * int(ideal_line['height'])
    common_area: int = 0
    dx = min(ideal_x_max, recognized_x_max) - max(ideal_x_min, recognized_x_min)
    dy = min(ideal_y_max, recognized_y_max) - max(ideal_y_min, recognized_y_min)
    if (dx >= 0) and (dy >= 0):
        common_area = dx * dy
    if (float(common_area) / float(ideal_area)) >= coordinate_percent:
        valid_box = True

    return valid_box

def validate_word(ideal_line: Line, recognized_line: Line, coordinate_percent: float, levenshtein_percent: int) -> bool:
    valid_input: bool = (
            ideal_line['left'] and
            ideal_line['top'] and
            ideal_line['width'] and
            ideal_line['height'] and
            ideal_line['word'] != '' and
            recognized_line['word'] != '' and
            recognized_line['left'] != '' and
            recognized_line['top'] != '' and
            recognized_line['width'] != '' and
            recognized_line['height'] != ''
        )

    if not valid_input:
        return False

    valid_box: bool = False

    ideal_area: float = int(ideal_line['width']) * int(ideal_line['height'])
    common_area: int = 0
    dx = min(int(ideal_line['width']), int(recognized_line['width'])) - max(int(ideal_line['left']), int(recognized_line['left']))
    dy = min(int(ideal_line['height']), int(recognized_line['height'])) - max(int(ideal_line['top']), int(recognized_line['top']))
    if (dx >= 0) and (dy >= 0):
        common_area = dx * dy
    if (float(common_area) / ideal_area) >= coordinate_percent:
        valid_box = True

    valid_levenshtein: bool = levenshtein.ratio(recognized_line['word'], ideal_line['word']) < levenshtein_percent

    return valid_box and valid_levenshtein

def normalize_word(word: str) -> str:
    alphanumeric: str = 'abcdefghijklmnopqrstuvwxyzABCDEFGHIJKLMNOPQRSTUVWXYZ0123456789'
    out: str = ''

    for char in word:
        if char in alphanumeric:
            out += char
    return out

if __name__ == '__main__':
    main()
