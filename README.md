# defi_ch: Cross-Chain Bridge Event Listener

This repository contains a Python-based simulation of a robust event listener and relayer, a critical component of a cross-chain bridge. This service monitors a source blockchain (e.g., Ethereum) for specific events, validates them, and relays the corresponding data to a destination chain.

## Concept

A cross-chain bridge allows users to transfer assets or data from one blockchain to another. A common mechanism for this is a "lock-and-mint" or "lock-and-unlock" model:

1.  A user **locks** assets in a smart contract on the **source chain**.
2.  This action emits an event (e.g., `TokensLocked`).
3.  A network of relayers (or oracles) listens for this event.
4.  Upon detecting a confirmed event, a relayer submits a transaction to the **destination chain** to mint or unlock an equivalent amount of a wrapped asset for the user.

This script simulates the **relayer** component (step 3 and 4). It is designed to be resilient, stateful, and capable of handling blockchain-specific issues like network latency and chain reorganizations (reorgs).

## Code Architecture

The application is structured into several distinct classes, each with a single responsibility, to ensure modularity and maintainability.

```
+-------------------+      +-----------------------+      +-------------------+
|   ConfigManager   |----->|   CrossChainRelayer   |<---->|      StateDB      |
| (Loads .env)      |      |   (Orchestrator)      |      | (state.json)      |
+-------------------+      +-----------+-----------+      +-------------------+
                                       |
                                       |
                         +-------------v-------------+
                         |       EventScanner        |
                         | (Scans for contract events) |
                         +-------------+-------------+
                                       |
                                       |
                         +-------------v-------------+
                         |    BlockchainConnector    |
                         |      (Manages Web3)       |
                         +---------------------------+
```

*   **`ConfigManager`**: Manages all configuration parameters. It loads settings like RPC URLs, contract addresses, and polling intervals from a `.env` file for security and flexibility.
*   **`StateDB`**: Handles the persistence of the application's state. It saves the last successfully scanned block number to a JSON file (`state.json`), allowing the service to resume from where it left off after a restart.
*   **`BlockchainConnector`**: Manages the connection to the source chain's RPC node using `web3.py`. It includes logic for checking connection status and attempting to reconnect if the connection is lost.
*   **`EventScanner`**: The core component for blockchain interaction. It uses a `web3.py` contract instance to efficiently query a range of blocks for a specific event (`TokensLocked`).
*   **`CrossChainRelayer`**: The main orchestrator. It coordinates the other components in a continuous loop:
    1.  Determines the correct block range to scan, accounting for block confirmations and potential reorgs.
    2.  Uses the `EventScanner` to fetch new events.
    3.  Processes and validates each event.
    4.  Relays the event data to the destination chain's API endpoint using the `requests` library.
    5.  Instructs `StateDB` to save the new state upon successful processing of a batch of blocks.

## How it Works

The service operates in an infinite loop, performing the following steps in each iteration:

1.  **Get Chain State**: It connects to the source chain's RPC node and fetches the latest block number.
2.  **Determine Scan Range**: It calculates a safe block range to scan.
    *   `to_block`: `latest_block_number - BLOCK_CONFIRMATIONS`. This ensures that we only process events from blocks that are unlikely to be reverted in a reorg.
    *   `from_block`: The last block scanned in the previous run (loaded from `state.json`), minus a few blocks for reorg safety. On the very first run, it starts from the current `to_block`.
3.  **Scan for Events**: It queries the source chain for `TokensLocked` events within the calculated block range.
4.  **Process and Relay**: If events are found, it iterates through them. Each event's data is formatted into a JSON payload and sent via a POST request to the destination chain's API endpoint.
5.  **Update State**: After scanning the block range (whether events were found or not), it saves the `to_block` value to `state.json`. This marks the range as processed and ensures the next iteration starts from the correct position.
6.  **Wait**: The service then pauses for a configurable interval (`POLL_INTERVAL_SECONDS`) before starting the next cycle.

This design ensures that events are processed reliably, exactly once, and in the correct order, even if the service is stopped and restarted.

## Usage Example

### 1. Prerequisites
- Python 3.8+
- An RPC URL for an Ethereum-compatible network (e.g., from [Infura](https://infura.io/) or [Alchemy](https://www.alchemy.com/)). This example is configured for Sepolia testnet.

### 2. Setup

First, clone the repository:
```bash
git clone https://github.com/your-username/defi_ch.git
cd defi_ch
```

Create a virtual environment and install the required dependencies:
```bash
python -m venv venv
source venv/bin/activate  # On Windows use `venv\Scripts\activate`
pip install -r requirements.txt
```

Create a `.env` file in the root directory and populate it with your configuration. You **must** provide a valid contract address to monitor.

```ini
# .env file

# RPC URL for the source blockchain (e.g., Ethereum Sepolia testnet)
SOURCE_CHAIN_RPC_URL="https://rpc.ankr.com/eth_sepolia"

# The address of the bridge smart contract to monitor on the source chain
# IMPORTANT: Replace the placeholder with a real contract address that emits a 'TokensLocked' event
BRIDGE_CONTRACT_ADDRESS="0xYourBridgeContractAddressHere"

# The API endpoint of the destination chain's relayer service
DESTINATION_CHAIN_API_ENDPOINT="https://httpbin.org/post" # Using httpbin.org for testing

# Time in seconds between polling for new blocks
POLL_INTERVAL_SECONDS=15

# Number of blocks to wait for finality before processing an event
BLOCK_CONFIRMATIONS=6
```

### 3. Running the Script

Execute the script from your terminal:
```bash
python script.py
```

### Example Output

The script will log its operations to the console.

```
2023-10-27 10:30:00,123 - INFO - Starting Cross-Chain Relayer Service...
2023-10-27 10:30:01,456 - INFO - Successfully connected to blockchain node at https://rpc.ankr.com/eth_sepolia. Chain ID: 11155111, Latest Block: 4500100
2023-10-27 10:30:01,457 - INFO - First run. Starting scan from block 4500094.
2023-10-27 10:30:01,457 - INFO - Scanning for 'TokensLocked' events from block 4500094 to 4500094...
2023-10-27 10:30:03,812 - INFO - Found 1 new 'TokensLocked' event(s).
2023-10-27 10:30:03,813 - INFO - Relaying event with txId: 0x... to destination chain...
2023-10-27 10:30:04,950 - INFO - Successfully relayed event 0x.... Destination API response: {...}
2023-10-27 10:30:04,955 - INFO - State successfully saved to 'state.json'.
2023-10-27 10:30:04,955 - DEBUG - Sleeping for 15 seconds...
```
