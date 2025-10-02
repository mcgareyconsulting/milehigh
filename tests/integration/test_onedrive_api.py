"""
Integration tests for OneDrive API interactions.
"""
import pytest
from unittest.mock import patch, Mock
import pandas as pd
from io import BytesIO
from app.onedrive.api import (
    get_access_token,
    get_excel_dataframe,
    get_last_modified_time,
    get_excel_data_with_timestamp,
    update_excel_cell
)


@pytest.mark.integration
@pytest.mark.api
@pytest.mark.onedrive
class TestOneDriveApiIntegration:
    """Integration tests for OneDrive API functions."""
    
    def test_get_access_token_success(self, mock_config, mock_requests):
        """Test successful access token retrieval."""
        expected_token = "test_access_token_12345"
        
        mock_requests['response'].json.return_value = {
            "access_token": expected_token,
            "token_type": "Bearer",
            "expires_in": 3600
        }
        
        result = get_access_token()
        
        # Verify API call
        mock_requests['post'].assert_called_once()
        call_args = mock_requests['post'].call_args
        
        # Check URL
        assert "test_tenant_id" in call_args[0][0]
        assert "oauth2/v2.0/token" in call_args[0][0]
        
        # Check data
        data = call_args[1]['data']
        assert data['grant_type'] == 'client_credentials'
        assert data['client_id'] == 'test_client_id'
        assert data['client_secret'] == 'test_client_secret'
        assert data['scope'] == 'https://graph.microsoft.com/.default'
        
        assert result == expected_token
    
    def test_get_access_token_error(self, mock_config, mock_requests):
        """Test access token retrieval with error."""
        import requests
        mock_requests['response'].raise_for_status.side_effect = requests.exceptions.HTTPError("401 Unauthorized")
        
        with pytest.raises(requests.exceptions.HTTPError):
            get_access_token()
    
    @patch('app.onedrive.api.get_access_token')
    @patch('app.onedrive.api.read_file_from_user_onedrive')
    @patch('pandas.read_excel')
    @patch('openpyxl.load_workbook')
    def test_get_excel_dataframe_success(self, mock_load_workbook, mock_read_excel, 
                                       mock_read_file, mock_get_token, mock_config):
        """Test successful Excel dataframe retrieval."""
        # Mock access token
        mock_get_token.return_value = "test_token"
        
        # Mock file content
        mock_read_file.return_value = b"fake_excel_content"
        
        # Mock pandas read_excel
        test_df = pd.DataFrame({
            "Job #": [123, 124],
            "Release #": [456, 457],
            "Job": ["Job 1", "Job 2"],
            "Description": ["Desc 1", "Desc 2"],
            "Start install": ["2024-01-15", "2024-01-16"]
        })
        mock_read_excel.return_value = test_df
        
        # Mock openpyxl workbook
        mock_ws = Mock()
        mock_ws.cell.return_value.value = "=TODAY()+7"
        mock_wb = Mock()
        mock_wb.sheetnames = ["Sheet1"]
        mock_wb.__getitem__.return_value = mock_ws
        mock_load_workbook.return_value = mock_wb
        
        result = get_excel_dataframe()
        
        # Verify function calls
        mock_get_token.assert_called_once()
        mock_read_file.assert_called_once_with("test_token", "test@example.com", "/test/file.xlsx")
        mock_read_excel.assert_called_once()
        mock_load_workbook.assert_called_once()
        
        # Check result
        assert isinstance(result, pd.DataFrame)
        assert len(result) == 2
        assert "start_install_formula" in result.columns
        assert "start_install_formulaTF" in result.columns
    
    def test_get_last_modified_time_success(self, mock_config, mock_requests):
        """Test successful last modified time retrieval."""
        expected_response = {
            "name": "test_file.xlsx",
            "id": "file_123",
            "lastModifiedDateTime": "2024-01-15T12:30:00.000Z",
            "size": 1024
        }
        
        mock_requests['response'].json.return_value = expected_response
        
        with patch('app.onedrive.api.get_access_token', return_value="test_token"):
            result = get_last_modified_time()
        
        # Verify API call
        mock_requests['get'].assert_called_once()
        call_args = mock_requests['get'].call_args
        
        # Check URL
        assert "test@example.com" in call_args[0][0]
        assert "/test/file.xlsx" in call_args[0][0]
        
        # Check headers
        headers = call_args[1]['headers']
        assert headers['Authorization'] == 'Bearer test_token'
        
        assert result == expected_response
    
    @patch('app.onedrive.api.get_last_modified_time')
    @patch('app.onedrive.api.get_excel_dataframe')
    def test_get_excel_data_with_timestamp(self, mock_get_df, mock_get_time):
        """Test getting Excel data with timestamp."""
        # Mock responses
        mock_get_time.return_value = {
            "name": "test_file.xlsx",
            "lastModifiedDateTime": "2024-01-15T12:30:00.000Z"
        }
        
        test_df = pd.DataFrame({"Job #": [123], "Release #": [456]})
        mock_get_df.return_value = test_df
        
        result = get_excel_data_with_timestamp()
        
        # Verify both functions were called
        mock_get_time.assert_called_once()
        mock_get_df.assert_called_once()
        
        # Check result structure
        assert "name" in result
        assert "last_modified_time" in result
        assert "data" in result
        assert result["name"] == "test_file.xlsx"
        assert result["last_modified_time"] == "2024-01-15T12:30:00.000Z"
        assert isinstance(result["data"], pd.DataFrame)
    
    def test_update_excel_cell_success(self, mock_config, mock_requests):
        """Test successful Excel cell update."""
        cell_address = "M15"
        value = "X"
        
        mock_requests['response'].status_code = 200
        
        with patch('app.onedrive.api.get_access_token', return_value="test_token"):
            result = update_excel_cell(cell_address, value)
        
        # Verify API call
        mock_requests['patch'].assert_called_once()
        call_args = mock_requests['patch'].call_args
        
        # Check URL
        url = call_args[0][0]
        assert "test@example.com" in url
        assert "/test/file.xlsx" in url
        assert "Job Log" in url  # Default worksheet name
        assert f"address='{cell_address}'" in url
        
        # Check headers
        headers = call_args[1]['headers']
        assert headers['Authorization'] == 'Bearer test_token'
        assert headers['Content-Type'] == 'application/json'
        
        # Check payload
        payload = call_args[1]['json']
        assert payload == {"values": [[value]]}
        
        assert result is True
    
    def test_update_excel_cell_custom_worksheet(self, mock_config, mock_requests):
        """Test Excel cell update with custom worksheet name."""
        cell_address = "N20"
        value = "O"
        worksheet_name = "Custom Sheet"
        
        mock_requests['response'].status_code = 200
        
        with patch('app.onedrive.api.get_access_token', return_value="test_token"):
            result = update_excel_cell(cell_address, value, worksheet_name)
        
        # Verify worksheet name in URL
        call_args = mock_requests['patch'].call_args
        url = call_args[0][0]
        assert worksheet_name in url
        
        assert result is True
    
    def test_update_excel_cell_api_error(self, mock_config, mock_requests):
        """Test Excel cell update with API error."""
        cell_address = "P25"
        value = "T"
        
        mock_requests['response'].status_code = 404
        mock_requests['response'].text = "File not found"
        
        with patch('app.onedrive.api.get_access_token', return_value="test_token"):
            result = update_excel_cell(cell_address, value)
        
        assert result is False
    
    def test_update_excel_cell_exception_handling(self, mock_config, mock_requests):
        """Test Excel cell update with exception."""
        cell_address = "Q30"
        value = "Y"
        
        with patch('app.onedrive.api.get_access_token', side_effect=Exception("Token error")):
            result = update_excel_cell(cell_address, value)
        
        assert result is False
    
    @patch('app.onedrive.api.get_access_token')
    def test_read_file_from_user_onedrive(self, mock_get_token, mock_config, mock_requests):
        """Test reading file from OneDrive."""
        from app.onedrive.api import read_file_from_user_onedrive
        
        mock_get_token.return_value = "test_token"
        mock_requests['response'].content = b"file_content"
        
        result = read_file_from_user_onedrive("test_token", "test@example.com", "/test/file.xlsx")
        
        # Verify API call
        mock_requests['get'].assert_called_once()
        call_args = mock_requests['get'].call_args
        
        # Check URL
        url = call_args[0][0]
        assert "test@example.com" in url
        assert "/test/file.xlsx" in url
        assert "/content" in url
        
        # Check headers
        headers = call_args[1]['headers']
        assert headers['Authorization'] == 'Bearer test_token'
        
        assert result == b"file_content"
    
    @patch('app.onedrive.api.get_access_token')
    def test_list_root_contents(self, mock_get_token, mock_config, mock_requests):
        """Test listing root contents of OneDrive."""
        from app.onedrive.api import list_root_contents
        
        mock_get_token.return_value = "test_token"
        expected_response = {
            "value": [
                {"name": "file1.xlsx", "id": "file1_id"},
                {"name": "file2.docx", "id": "file2_id"}
            ]
        }
        mock_requests['response'].json.return_value = expected_response
        
        result = list_root_contents("test_token", "test@example.com")
        
        # Verify API call
        mock_requests['get'].assert_called_once()
        call_args = mock_requests['get'].call_args
        
        # Check URL
        url = call_args[0][0]
        assert "test@example.com" in url
        assert "/root/children" in url
        
        assert result == expected_response
