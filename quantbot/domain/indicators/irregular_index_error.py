# quantbot/domain/indicators/irregular_index_error.py
class IrregularIndexError(ValueError):
    """索引不是等間隔的完整時間網格，rolling 的視窗會涵蓋比預期更長的時間。"""
