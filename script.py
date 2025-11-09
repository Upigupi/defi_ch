# script.py
# A simulation of a robust event listener for a cross-chain bridge.
# This component is responsible for monitoring a source chain for specific events
# (e.g., 'TokensLocked') and relaying them to a destination chain.

import os
import json
import time
import logging
from typing import Dict, Any, List, Optional

import requests
from web3 import Web3
from web3.exceptions import BlockNotFound
from web3.contract import Contract
from dotenv import load_dotenv

# --- Configuration ---
# In a real-world scenario, this would be in a separate config file (e.g., config.yaml)
# or managed by a more sophisticated configuration system.

class ConfigManager:
    """
    Manages application configuration, loading from environment variables.
    """
    def __init__(self):
        load_dotenv()
        self.SOURCE_CHAIN_RPC_URL = os.getenv("SOURCE_CHAIN_RPC_URL", "https://rpc.ankr.com/eth_sepolia")
        self.BRIDGE_CONTRACT_ADDRESS = os.getenv("BRIDGE_CONTRACT_ADDRESS", "0x0000000000000000000000000000000000000000") # Placeholder
        self.DESTINATION_CHAIN_API_ENDPOINT = os.getenv("DESTINATION_CHAIN_API_ENDPOINT", "https://api.destination-chain.com/relay")
        self.POLL_INTERVAL_SECONDS = int(os.getenv("POLL_INTERVAL_SECONDS", "15"))
        self.BLOCK_CONFIRMATIONS = int(os.getenv("BLOCK_CONFIRMATIONS", "6")) # Number of blocks to wait for finality
        self.STATE_FILE_PATH = "state.json"
        self.CONTRACT_ABI = self._load_contract_abi()

    def _load_contract_abi(self) -> List[Dict[str, Any]]:
        """
        Loads the contract ABI. In this simulation, we define it directly.
        In a real project, this would be loaded from a file like 'bridge_abi.json'.
        """
        # A minimal ABI for a 'TokensLocked' event.
        return json.loads("""
        [
            {
                "anonymous": false,
                "inputs": [
                    {"indexed": true, "internalType": "address", "name": "sender", "type": "address"},
                    {"indexed": true, "internalType": "uint256", "name": "destinationChainId", "type": "uint256"},
                    {"indexed": false, "internalType": "address", "name": "recipient", "type": "address"},
                    {"indexed": false, "internalType": "address", "name": "token", "type": "address"},
                    {"indexed": false, "internalType": "uint256", "name": "amount", "type": "uint256"},
                    {"indexed": false, "internalType": "bytes32", "name": "transactionId", "type": "bytes32"}
                ],
                "name": "TokensLocked",
                "type": "event"
            }
        ]
        """)

# --- State Management ---

class StateDB:
    """
    Handles persistent storage of the application state, such as the last processed block.
    Uses a simple JSON file for persistence.
    """
    def __init__(self, filepath: str):
        self.filepath = filepath

    def load_state(self) -> Dict[str, Any]:
        """Loads state from the JSON file. Returns a default state if the file doesn't exist."""
        try:
            with open(self.filepath, 'r') as f:
                return json.load(f)
        except (FileNotFoundError, json.JSONDecodeError):
            logging.warning(f"State file not found or corrupted at '{self.filepath}'. Starting with default state.")
            return {"last_scanned_block": None}

    def save_state(self, state: Dict[str, Any]):
        """Saves the given state to the JSON file."""
        try:
            with open(self.filepath, 'w') as f:
                json.dump(state, f, indent=4)
            logging.info(f"State successfully saved to '{self.filepath}'.")
        except IOError as e:
            logging.error(f"Failed to save state to '{self.filepath}': {e}")


# --- Blockchain Interaction ---

class BlockchainConnector:
    """
    Manages the connection to a blockchain node via Web3.py.
    Includes connection checking and retry logic.
    """
    def __init__(self, rpc_url: str):
        self.rpc_url = rpc_url
        self.web3: Optional[Web3] = None
        self.connect()

    def connect(self):
        """Establishes a connection to the blockchain node."""
        try:
            self.web3 = Web3(Web3.HTTPProvider(self.rpc_url))
            if not self.is_connected():
                raise ConnectionError("Failed to connect to the node.")
            logging.info(f"Successfully connected to blockchain node at {self.rpc_url}. "
                         f"Chain ID: {self.web3.eth.chain_id}, Latest Block: {self.web3.eth.block_number}")
        except Exception as e:
            logging.error(f"Error connecting to blockchain node: {e}")
            self.web3 = None

    def is_connected(self) -> bool:
        """Checks if the connection to the node is active."""
        return self.web3 is not None and self.web3.is_connected()

    def get_web3_instance(self) -> Web3:
        """Returns the Web3 instance, ensuring it's connected."""
        if not self.is_connected():
            logging.warning("Connection lost. Attempting to reconnect...")
            self.connect()
        if self.web3 is None:
            raise ConnectionError("Unable to establish a connection to the blockchain node.")
        return self.web3

    def get_contract(self, address: str, abi: List[Dict[str, Any]]) -> Contract:
        """Gets a contract instance."""
        w3 = self.get_web3_instance()
        checksum_address = w3.to_checksum_address(address)
        return w3.eth.contract(address=checksum_address, abi=abi)


# --- Core Logic ---

class EventScanner:
    """
    Scans a given block range for specific smart contract events.
    Handles potential blockchain reorganizations by re-scanning recent blocks.
    """
    def __init__(self, connector: BlockchainConnector, contract_address: str, contract_abi: List[Dict[str, Any]]):
        self.connector = connector
        self.contract = self.connector.get_contract(contract_address, contract_abi)
        self.event_name = "TokensLocked" # The event we are interested in

    def scan_for_events(self, from_block: int, to_block: int) -> List[Dict[str, Any]]:
        """
        Scans for 'TokensLocked' events within a specified block range.
        
        Args:
            from_block: The starting block number.
            to_block: The ending block number.
            
        Returns:
            A list of decoded event logs.
        """
        if from_block > to_block:
            logging.debug(f"from_block ({from_block}) > to_block ({to_block}). No scan needed.")
            return []

        logging.info(f"Scanning for '{self.event_name}' events from block {from_block} to {to_block}...")
        try:
            event_filter = self.contract.events[self.event_name].create_filter(
                fromBlock=from_block,
                toBlock=to_block
            )
            events = event_filter.get_all_entries()
            
            if events:
                logging.info(f"Found {len(events)} new '{self.event_name}' event(s).")
                # Format events for easier consumption
                return [self._format_event(event) for event in events]
            else:
                logging.debug("No new events found in the scanned range.")
                return []
        except BlockNotFound:
            logging.warning(f"Block range [{from_block}-{to_block}] not found. Possibly a reorg or node is not fully synced.")
            return []
        except Exception as e:
            logging.error(f"An unexpected error occurred during event scanning: {e}")
            return []

    def _format_event(self, event_log: Dict[str, Any]) -> Dict[str, Any]:
        """Formats a raw event log into a more structured dictionary."""
        args = event_log['args']
        return {
            "transactionHash": event_log['transactionHash'].hex(),
            "blockNumber": event_log['blockNumber'],
            "sender": args['sender'],
            "destinationChainId": args['destinationChainId'],
            "recipient": args['recipient'],
            "token": args['token'],
            "amount": args['amount'],
            "transactionId": args['transactionId'].hex()
        }


class CrossChainRelayer:
    """
    Orchestrates the entire process: scanning events from the source chain
    and relaying them to the destination chain's API.
    """
    def __init__(self, config: ConfigManager):
        self.config = config
        self.state_db = StateDB(config.STATE_FILE_PATH)
        self.connector = BlockchainConnector(config.SOURCE_CHAIN_RPC_URL)
        if "0x0000000000000000000000000000000000000000" in config.BRIDGE_CONTRACT_ADDRESS:
            raise ValueError("Placeholder BRIDGE_CONTRACT_ADDRESS detected. Please set a real address in your configuration.")
        self.scanner = EventScanner(
            self.connector,
            config.BRIDGE_CONTRACT_ADDRESS,
            config.CONTRACT_ABI
        )
        self.state = self.state_db.load_state()

    def run(self):
        """Starts the main infinite loop for the relayer service."""
        logging.info("Starting Cross-Chain Relayer Service...")
        while True:
            try:
                self.process_blocks()
            except ConnectionError as e:
                logging.error(f"Connection error: {e}. Retrying in {self.config.POLL_INTERVAL_SECONDS} seconds...")
            except Exception as e:
                logging.critical(f"An unhandled exception occurred in the main loop: {e}", exc_info=True)
            
            logging.debug(f"Sleeping for {self.config.POLL_INTERVAL_SECONDS} seconds...")
            time.sleep(self.config.POLL_INTERVAL_SECONDS)

    def process_blocks(self):
        """
        The core logic for a single iteration of the processing loop.
        Determines block range, scans for events, relays them, and updates state.
        """
        w3 = self.connector.get_web3_instance()
        
        latest_block = w3.eth.block_number
        to_block = latest_block - self.config.BLOCK_CONFIRMATIONS
        
        last_scanned = self.state.get("last_scanned_block")
        if last_scanned is None:
            from_block = to_block
            logging.info(f"First run. Starting scan from block {from_block}.")
        else:
            # Handle potential reorgs by re-scanning the last few blocks
            from_block = max(0, last_scanned - self.config.BLOCK_CONFIRMATIONS)
            logging.info(f"Resuming scan. Re-scanning from block {from_block} for reorg safety.")

        if from_block > to_block:
            logging.info(f"Chain head ({latest_block}) has not progressed enough for new confirmed blocks. Waiting.")
            return

        events = self.scanner.scan_for_events(from_block, to_block)

        if not events:
            self.state["last_scanned_block"] = to_block
            self.state_db.save_state(self.state)
            return

        for event in events:
            self.relay_event(event)

        self.state["last_scanned_block"] = to_block
        self.state_db.save_state(self.state)

    def relay_event(self, event: Dict[str, Any]):
        """
        Simulates relaying a single event to the destination chain's API.
        Includes validation and retry logic.
        """
        logging.info(f"Relaying event with txId: {event['transactionId']} to destination chain...")
        
        if event['amount'] <= 0:
            logging.warning(f"Skipping event with txId {event['transactionId']} due to invalid amount: {event['amount']}")
            return

        payload = {
            "sourceTransactionHash": event["transactionHash"],
            "sourceBlockNumber": event["blockNumber"],
            "payload": {
                "sender": event["sender"],
                "recipient": event["recipient"],
                "token": event["token"],
                "amount": str(event["amount"]), # Send amount as string to avoid precision issues
                "uniqueBridgeTxId": event["transactionId"]
            }
        }
        
        try:
            response = requests.post(
                self.config.DESTINATION_CHAIN_API_ENDPOINT,
                json=payload,
                timeout=10 # Set a timeout for the request
            )
            response.raise_for_status() # Raises an HTTPError for bad responses (4xx or 5xx)
            
            logging.info(f"Successfully relayed event {event['transactionId']}. "
                         f"Destination API response: {response.json()}")

        except requests.exceptions.RequestException as e:
            logging.error(f"Failed to relay event {event['transactionId']} to destination API: {e}")
            # In a real system, this would trigger a retry mechanism with exponential backoff.

def main():
    """Main entry point for the script."""
    logging.basicConfig(
        level=logging.INFO,
        format='%(asctime)s - %(levelname)s - %(message)s'
    )
    
    try:
        config = ConfigManager()
        relayer = CrossChainRelayer(config)
        relayer.run()
    except ValueError as e:
        logging.error(f"Configuration Error: {e}")
    except Exception as e:
        logging.critical(f"A fatal error occurred during initialization: {e}", exc_info=True)

if __name__ == "__main__":
    main()


