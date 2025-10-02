"""
Integration tests for Trello API interactions.
"""
import pytest
from unittest.mock import patch, Mock
from datetime import date, datetime
from app.trello.api import (
    update_trello_card,
    get_list_name_by_id,
    get_list_by_name,
    get_trello_card_by_id,
    get_trello_cards_from_subset
)


@pytest.mark.integration
@pytest.mark.api
@pytest.mark.trello
class TestTrelloApiIntegration:
    """Integration tests for Trello API functions."""
    
    def test_update_trello_card_success(self, mock_config, mock_requests):
        """Test successful Trello card update."""
        card_id = "test_card_123"
        new_list_id = "new_list_456"
        new_due_date = date(2024, 2, 1)
        
        # Mock successful response
        mock_requests['response'].json.return_value = {
            "id": card_id,
            "idList": new_list_id,
            "due": "2024-02-01T18:00:00.000Z"
        }
        
        result = update_trello_card(card_id, new_list_id, new_due_date)
        
        # Verify API was called correctly
        mock_requests['put'].assert_called_once()
        call_args = mock_requests['put'].call_args
        
        # Check URL
        assert card_id in call_args[0][0]
        
        # Check parameters
        params = call_args[1]['params']
        assert params['key'] == 'test_api_key'
        assert params['token'] == 'test_token'
        assert params['idList'] == new_list_id
        assert 'due' in params
        
        # Check response
        assert result['id'] == card_id
        assert result['idList'] == new_list_id
    
    def test_update_trello_card_clear_due_date(self, mock_config, mock_requests):
        """Test updating Trello card with cleared due date."""
        card_id = "test_card_123"
        new_list_id = "new_list_456"
        
        mock_requests['response'].json.return_value = {"id": card_id}
        
        update_trello_card(card_id, new_list_id, None)
        
        # Verify due date was set to None
        call_args = mock_requests['put'].call_args
        params = call_args[1]['params']
        assert params['due'] is None
    
    def test_update_trello_card_http_error(self, mock_config, mock_requests):
        """Test Trello card update with HTTP error."""
        card_id = "test_card_123"
        
        # Mock HTTP error
        import requests
        mock_requests['response'].raise_for_status.side_effect = requests.exceptions.HTTPError("404 Not Found")
        mock_requests['response'].text = "Card not found"
        
        with pytest.raises(requests.exceptions.HTTPError):
            update_trello_card(card_id, "new_list", date(2024, 2, 1))
    
    def test_get_list_name_by_id_success(self, mock_config, mock_requests):
        """Test successful list name retrieval."""
        list_id = "test_list_123"
        expected_name = "In Progress"
        
        mock_requests['response'].json.return_value = {
            "id": list_id,
            "name": expected_name
        }
        
        result = get_list_name_by_id(list_id)
        
        # Verify API call
        mock_requests['get'].assert_called_once()
        call_args = mock_requests['get'].call_args
        assert list_id in call_args[0][0]
        
        params = call_args[1]['params']
        assert params['key'] == 'test_api_key'
        assert params['token'] == 'test_token'
        
        assert result == expected_name
    
    def test_get_list_name_by_id_error(self, mock_config, mock_requests):
        """Test list name retrieval with API error."""
        list_id = "invalid_list"
        
        mock_requests['response'].status_code = 404
        mock_requests['response'].text = "List not found"
        
        result = get_list_name_by_id(list_id)
        assert result is None
    
    def test_get_list_by_name_success(self, mock_config, mock_requests):
        """Test successful list retrieval by name."""
        list_name = "Paint complete"
        expected_id = "list_123"
        
        mock_requests['response'].json.return_value = [
            {"id": "list_456", "name": "In Progress"},
            {"id": expected_id, "name": list_name},
            {"id": "list_789", "name": "Completed"}
        ]
        
        result = get_list_by_name(list_name)
        
        # Verify API call to board lists endpoint
        mock_requests['get'].assert_called_once()
        call_args = mock_requests['get'].call_args
        assert "test_board_id" in call_args[0][0]
        assert "lists" in call_args[0][0]
        
        assert result == {"name": list_name, "id": expected_id}
    
    def test_get_list_by_name_not_found(self, mock_config, mock_requests):
        """Test list retrieval by name when not found."""
        mock_requests['response'].json.return_value = [
            {"id": "list_456", "name": "In Progress"},
            {"id": "list_789", "name": "Completed"}
        ]
        
        result = get_list_by_name("Nonexistent List")
        assert result is None
    
    def test_get_trello_card_by_id_success(self, mock_config, mock_requests):
        """Test successful card retrieval by ID."""
        card_id = "test_card_123"
        expected_card = {
            "id": card_id,
            "name": "123-456 Test Job",
            "desc": "Test description",
            "idList": "list_123",
            "due": "2024-02-01T18:00:00.000Z"
        }
        
        mock_requests['response'].json.return_value = expected_card
        
        result = get_trello_card_by_id(card_id)
        
        # Verify API call
        mock_requests['get'].assert_called_once()
        call_args = mock_requests['get'].call_args
        assert card_id in call_args[0][0]
        
        assert result == expected_card
    
    def test_get_trello_card_by_id_error(self, mock_config, mock_requests):
        """Test card retrieval with API error."""
        card_id = "invalid_card"
        
        mock_requests['response'].status_code = 404
        mock_requests['response'].text = "Card not found"
        
        result = get_trello_card_by_id(card_id)
        assert result is None
    
    def test_get_trello_cards_from_subset_success(self, mock_config, mock_requests):
        """Test retrieving cards from target lists."""
        # Mock lists response
        lists_response = [
            {"id": "list_1", "name": "Fit Up Complete."},
            {"id": "list_2", "name": "Paint complete"},
            {"id": "list_3", "name": "Shipping completed"},
            {"id": "list_4", "name": "Other List"}
        ]
        
        # Mock cards response
        cards_response = [
            {
                "id": "card_1",
                "name": "123-456 Job 1",
                "desc": "Description 1",
                "idList": "list_1",
                "due": "2024-02-01T18:00:00.000Z",
                "labels": []
            },
            {
                "id": "card_2",
                "name": "124-457 Job 2",
                "desc": "Description 2",
                "idList": "list_2",
                "due": None,
                "labels": [{"name": "Priority"}]
            },
            {
                "id": "card_3",
                "name": "125-458 Job 3",
                "desc": "Description 3",
                "idList": "list_4",  # Not in target lists
                "due": None,
                "labels": []
            }
        ]
        
        # Mock the two API calls
        def mock_get_side_effect(url, **kwargs):
            response = Mock()
            response.raise_for_status.return_value = None
            
            if "lists" in url:
                response.json.return_value = lists_response
            elif "cards" in url:
                response.json.return_value = cards_response
            
            return response
        
        mock_requests['get'].side_effect = mock_get_side_effect
        
        result = get_trello_cards_from_subset()
        
        # Should have called API twice (lists and cards)
        assert mock_requests['get'].call_count == 2
        
        # Should only return cards from target lists
        assert len(result) == 2
        
        # Check first card
        card_1 = next(card for card in result if card["id"] == "card_1")
        assert card_1["name"] == "123-456 Job 1"
        assert card_1["list_name"] == "Fit Up Complete."
        assert card_1["due"] == "2024-02-01T18:00:00.000Z"
        assert card_1["labels"] == []
        
        # Check second card
        card_2 = next(card for card in result if card["id"] == "card_2")
        assert card_2["name"] == "124-457 Job 2"
        assert card_2["list_name"] == "Paint complete"
        assert card_2["due"] is None
        assert card_2["labels"] == ["Priority"]
        
        # Card 3 should not be included (not in target lists)
        card_3_found = any(card["id"] == "card_3" for card in result)
        assert not card_3_found
    
    def test_get_trello_cards_from_subset_api_error(self, mock_config, mock_requests):
        """Test cards retrieval with API error."""
        import requests
        mock_requests['get'].side_effect = requests.exceptions.HTTPError("API Error")
        
        with pytest.raises(requests.exceptions.HTTPError):
            get_trello_cards_from_subset()
