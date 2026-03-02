from unittest.mock import patch, MagicMock
from app.services.google_sheets import get_row_data, update_post_status, COLUMNS


def _make_mock_worksheet(row_values):
    """Helper to create a mock worksheet with given row values"""
    mock_ws = MagicMock()
    mock_ws.row_values.return_value = row_values
    mock_spreadsheet = MagicMock()
    mock_spreadsheet.sheet1 = mock_ws
    return mock_spreadsheet, mock_ws


@patch("app.services.google_sheets.get_sheet_client")
def test_get_row_data(mock_client):
    row = ["1", "", "account1", "2026/03/01", "", "instagram", "テーマ", "フック",
           "台本", "IG caption text", "TikTok caption text", "#tag1 #tag2", ""]
    mock_spreadsheet, _ = _make_mock_worksheet(row)
    mock_client.return_value = mock_spreadsheet

    result = get_row_data(2)
    assert result.row_number == 2
    assert result.ig_caption == "IG caption text"
    assert result.tiktok_caption == "TikTok caption text"
    assert result.hashtags == "#tag1 #tag2"
    assert result.platform == "instagram"


@patch("app.services.google_sheets.get_sheet_client")
def test_get_row_data_short_row(mock_client):
    """Row with fewer than 13 columns should be padded"""
    row = ["1", "", "account1"]
    mock_spreadsheet, _ = _make_mock_worksheet(row)
    mock_client.return_value = mock_spreadsheet

    result = get_row_data(2)
    assert result.ig_caption == ""
    assert result.hashtags == ""


@patch("app.services.google_sheets.get_sheet_client")
def test_update_post_status(mock_client):
    mock_spreadsheet, mock_ws = _make_mock_worksheet([])
    mock_client.return_value = mock_spreadsheet

    update_post_status(3)

    # Status column B = index 1, so cell column = 2
    mock_ws.update_cell.assert_any_call(3, COLUMNS["status"] + 1, "投稿済み")
    # Posted date column E = index 4, so cell column = 5
    assert mock_ws.update_cell.call_count == 2
