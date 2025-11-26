from typing import Callable, List, Optional

class PriceNotFoundError(Exception):
    """Custom exception raised when no provider can find a price for a given token."""
    def __init__(self, token_symbol: str):
        self.token_symbol = token_symbol
        super().__init__(f"Could not retrieve price for token: {token_symbol}")

class PriceAggregator:
    """
    Aggregates token prices from a list of provider functions.

    This class iterates through a prioritized list of price providers. It returns
    the price from the first provider that successfully retrieves it, making the
    price fetching mechanism more resilient to single-source failures.
    """

    def __init__(self, providers: List[Callable[[str], Optional[float]]]):
        """
        Initializes the PriceAggregator with a list of price providers.

        Args:
            providers: A list of callable functions. Each function should accept
                       a token symbol (str) as an argument and return its price (float)
                       or None if the price cannot be found. The list is treated
                       as a priority list, from highest to lowest.
        """
        if not providers:
            raise ValueError("At least one price provider must be supplied.")
        self.providers = providers

    def get_price(self, token_symbol: str) -> float:
        """
        Attempts to get the price for a given token symbol from the configured providers.

        It iterates through the providers in the order they were supplied. The first
        non-None, positive price returned by a provider is returned immediately.

        Args:
            token_symbol: The symbol of the token (e.g., 'ETH', 'BTC').

        Returns:
            The price of the token as a float.

        Raises:
            PriceNotFoundError: If none of the configured providers can find a price
                                for the given token symbol.
        """
        for i, provider in enumerate(self.providers):
            try:
                price = provider(token_symbol)
                if price is not None and isinstance(price, (int, float)) and price > 0:
                    return float(price)
            except Exception as e:
                # Optionally log the error from the failing provider
                # print(f"Warning: Provider #{i+1} failed for {token_symbol}: {e}")
                pass
        
        raise PriceNotFoundError(token_symbol)

# Example Usage
if __name__ == '__main__':
    # --- Mock Price Providers ---
    def mock_api_1(token: str) -> Optional[float]:
        print(f"-> Querying Mock Provider API 1 for {token}...")
        prices = {"ETH": 3000.50, "BTC": 60000.75}
        if token == "SOL":
            raise ConnectionError("API 1 is down for SOL")
        return prices.get(token)

    def mock_api_2(token: str) -> Optional[float]:
        print(f"-> Querying Mock Provider API 2 for {token}...")
        prices = {"ETH": 3001.00, "SOL": 150.25, "BTC": None} # Inconsistent data for BTC
        return prices.get(token)

    def mock_cache(token: str) -> Optional[float]:
        print(f"-> Querying Mock Provider Cache for {token}...")
        prices = {"ETH": 2999.00, "SOL": 149.99, "LINK": 18.50}
        return prices.get(token)

    # --- Aggregator Setup ---
    provider_list = [mock_api_1, mock_api_2, mock_cache]
    aggregator = PriceAggregator(providers=provider_list)

    # --- Test Cases ---
    tokens_to_fetch = ["ETH", "SOL", "LINK", "ADA"]

    for token in tokens_to_fetch:
        print("-" * 20)
        try:
            price = aggregator.get_price(token)
            print(f"✅ SUCCESS: Final aggregated price for {token}: ${price}\n")
        except PriceNotFoundError as e:
            print(f"❌ FAILED: {e}\n")
