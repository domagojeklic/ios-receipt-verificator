from flask import Flask
from flask import request
from flask import jsonify
import logging
import requests
import os
import sys

# Shared Secret environment variable
APP_SHARED_SECRET = 'APP_SHARED_SECRET'

# Apple servers URLs
VERIFICATOR_URL_SANDBOX = 'https://sandbox.itunes.apple.com/verifyReceipt'
VERIFICATOR_URL_PRODUCTION = 'https://buy.itunes.apple.com/verifyReceipt'

# Applications bundle identifier
APP_BUNDLE_ID = 'com.microblink.PhotoMath'

# Verification request keys
VERIFICATION_REQUEST_RECEIPT = 'receipt'
VERIFICATION_REQUEST_TRANSACTION_ID = 'transactionId'
VERIFICATION_REQUEST_ORIGINAL_TRANSACTION_ID = 'originalTransactionId'

# Verification response keys
VERIFICATION_RESPONSE_VALID = 'isValid'
VERIFICATION_RESPONSE_EXPIRATION_DATE = 'expiration'
VERIFICATION_RESPONSE_SANDBOX = 'sandbox'

# Request keys for Apple servers
APPLE_REQUEST_RECEIPT = 'receipt-data'
APPLE_REQUEST_PASSWORD = 'password'
APPLE_REQUEST_EXCLUDE_OLD = 'exclude-old-transactions'

# Receipt keys
RECEIPT_KEY_STATUS = 'status'
RECEIPT_VALUE_STATUS_VALID = 0
RECEIPT_VALUE_STATUS_SANDBOX = 21007
RECEIPT_KEY_RECEIPT = 'receipt'
RECEIPT_KEY_LATEST_RECEIPT_INFO = 'latest_receipt_info'
RECEIPT_KEY_BUNDLE_ID = 'bundle_id'
RECEIPT_KEY_IN_APP = 'in_app'
RECEIPT_KEY_TRANSACTION_ID = 'transaction_id'
RECEIPT_KEY_ORIGINAL_TRANSACTION_ID = 'original_transaction_id'
RECEIPT_KEY_EXPIRE_DATE_MS = 'expires_date_ms'

app = Flask(__name__)

logging.basicConfig(level=logging.DEBUG)

# First to get shared secret from argument, then from env var
app_shared_secret = sys.argv[1] if len(sys.argv) > 1 else os.environ.get(APP_SHARED_SECRET)
	
if not app_shared_secret:
	raise RuntimeError('Please specify shared secret as {} environment variable or pass it as the first argument to this script'.format(APP_SHARED_SECRET))

@app.route('/test')
@app.route('/')
def test():
	return 'Server is working!'

@app.route('/refresh', methods=['POST'])
def refresh():
	'''
		Endpoint for refreshing receipt
		Returns verification status and latest expiration date of any transaction

		Request JSON parameters:
			• receipt - base64 encoded device receipt

		Response JSON parameters:
			• isValid - verification status (valid / invalid)
			• expiration - latest expiration epoch time for transactions with original transactionId
		
	'''
	json = request.get_json()

	receipt = json[VERIFICATION_REQUEST_RECEIPT]

	app.logger.debug('Refreshing receipt')

	(apple_response, isSandbox) = send_receipt_to_apple(receipt)

	(valid, expiration_date) = refresh_receipt(apple_response)

	response = {
		VERIFICATION_RESPONSE_VALID : valid
	}

	response = create_response(valid, expiration_date, isSandbox)

	return response

@app.route('/restore', methods=['POST'])
def restore():
	'''
		Endpoint for verifying restored transactions
		Returns verification status and latest expiration date based on original transaction identifier

		Request JSON parameters:
			• receipt - base64 encoded device receipt
			• transactionId - original transactionId

		Response JSON parameters:
			• isValid - verification status (valid / invalid)
			• expiration - latest expiration epoch time for transactions with original transactionId
		
	'''
	json = request.get_json()

	receipt = json[VERIFICATION_REQUEST_RECEIPT]
	transaction_id = json[VERIFICATION_REQUEST_TRANSACTION_ID]

	app.logger.debug('Restoring transaction with original transactionId: {0}'.format(transaction_id))

	(apple_response, isSandbox) = send_receipt_to_apple(receipt)

	(valid, expiration_date) = restore_receipt(apple_response, transaction_id)

	response = {
		VERIFICATION_RESPONSE_VALID : valid
	}

	response = create_response(valid, expiration_date, isSandbox)

	return response

@app.route('/verify', methods=['POST'])
def verify():
	'''
		Endpoint for verifying purchased transactions
		Returns verification status and expiration date based on transaction identifier

		Request JSON parameters:
			• receipt - base64 encoded device receipt
			• transactionId - original transactionId

		Response JSON parameters:
			• isValid - verification status (valid / invalid)
			• expiration - expiration epoch time for transactions with transactionId
		
	'''
	json = request.get_json()

	receipt = json[VERIFICATION_REQUEST_RECEIPT]
	transaction_id = json[VERIFICATION_REQUEST_TRANSACTION_ID]
	original_transaction_id = json[VERIFICATION_REQUEST_ORIGINAL_TRANSACTION_ID]

	app.logger.debug('Verifiying  transaction with transactionId: {0} original transactionId: {1}'.format(transaction_id, original_transaction_id))

	(apple_response, isSandbox) = send_receipt_to_apple(receipt)

	(valid, expiration_date) = verify_receipt(apple_response, transaction_id, original_transaction_id)

	response = create_response(valid, expiration_date, isSandbox)

	return response

def create_response(verification_status, expiration_date, isSandbox):
	'''
		Creates JSON response based on verification_status and expiration_date
	'''
	
	response = {
		VERIFICATION_RESPONSE_VALID : verification_status,
		VERIFICATION_RESPONSE_SANDBOX : isSandbox
	}

	if not expiration_date == None:
		response[VERIFICATION_RESPONSE_EXPIRATION_DATE] = expiration_date

	return jsonify(response)
	
def send_receipt_to_apple(receipt):
	'''
		Sends base64 encoded receipt to apple servers and returns decripted receipt JSON
	'''

	app.logger.debug('Sending receipt to apple servers')

	payload = {
		APPLE_REQUEST_RECEIPT : receipt,
		APPLE_REQUEST_PASSWORD : app_shared_secret,
		APPLE_REQUEST_EXCLUDE_OLD : True
	}

	isSandbox = False

	# Receipt should always be verified with production servers first (Sandbox = False)
	server_url = verification_server_url(False)
	response = requests.post(server_url, json=payload)
	response_dict = response.json()

	if response_dict.get(RECEIPT_KEY_STATUS) == RECEIPT_VALUE_STATUS_SANDBOX:
		app.logger.debug('This receipt is from the test environment. Sending request to sandbox servers!')
		isSandbox = True
		server_url = verification_server_url(True)
		response = requests.post(server_url, json=payload)
		response_dict = response.json()

	app.logger.debug('Received response from apple: \n{0}'.format(response.text))

	return (response_dict, isSandbox)

def verification_server_url(sandbox):
	'''
		Returns verification server URL
	'''
	return VERIFICATOR_URL_SANDBOX if sandbox else VERIFICATOR_URL_PRODUCTION

def verify_receipt(receipt, transaction_id, original_transaction_id):
	'''
		Verifies whether the bundleId is valid and whether the transactionId is inside the list of transactions.
		Returns verification status (valid/invalid) and expiration date in case of a valid transaction or None otherwise
	'''

	# Receipt status check 
	status_valid = receipt[RECEIPT_KEY_STATUS] == RECEIPT_VALUE_STATUS_VALID

	if not status_valid:
		app.logger.debug('Receipt status NOT valid')
		return(False, None)

	# Bundle identifier check
	bundle_id_valid = receipt[RECEIPT_KEY_RECEIPT][RECEIPT_KEY_BUNDLE_ID] == APP_BUNDLE_ID

	if not bundle_id_valid:
		app.logger.debug('BundleId NOT valid')
		return (False, None)

	app.logger.debug('BundleId valid')

	# Transaction id check
	epoch_time = 0

	if RECEIPT_KEY_LATEST_RECEIPT_INFO in receipt:
		latest_receipt_info = receipt[RECEIPT_KEY_LATEST_RECEIPT_INFO]
		for transaction in latest_receipt_info:
			# Original transaction IDs should always match
			if transaction[RECEIPT_KEY_ORIGINAL_TRANSACTION_ID] == original_transaction_id:
				# If transaction IDs do not match we raise an error but we still verify transaction as valid 
				if transaction[RECEIPT_KEY_TRANSACTION_ID] != transaction_id:
					app.logger.error('TransactionIDs do not match {}')

				transaction_epoch_ms = transaction[RECEIPT_KEY_EXPIRE_DATE_MS]
				epoch_time = float(transaction_epoch_ms) / 1000
				break
	
	if epoch_time > 0:
		return (True, epoch_time)
	else:
		return (False, None)

	return (False, None)

def restore_receipt(receipt, original_transaction_id):
	'''
		Verifies whether the bundleId is valid and whether there is at least one transactions with original_transaction_id.
		Returns verification status (valid/invalid) and latest expiration date in case of a valid transaction or None otherwise
	'''

	# Receipt status check 
	status_valid = receipt[RECEIPT_KEY_STATUS] == RECEIPT_VALUE_STATUS_VALID

	if not status_valid:
		app.logger.debug('Receipt status NOT valid')
		return(False, None)

	# Bundle identifier check
	bundle_id_valid = receipt[RECEIPT_KEY_RECEIPT][RECEIPT_KEY_BUNDLE_ID] == APP_BUNDLE_ID

	if not bundle_id_valid:
		app.logger.debug('BundleId NOT valid')
		return (False, None)

	app.logger.debug('BundleId valid')

	epoch_time = 0
	transactions = receipt[RECEIPT_KEY_RECEIPT][RECEIPT_KEY_IN_APP]

	for transaction in transactions:
		if transaction[RECEIPT_KEY_ORIGINAL_TRANSACTION_ID] == original_transaction_id:
			transaction_epoch_ms = transaction[RECEIPT_KEY_EXPIRE_DATE_MS]
			transaction_epoch = float(transaction_epoch_ms) / 1000
			if transaction_epoch > epoch_time:
				epoch_time = transaction_epoch

	if epoch_time > 0:
		return (True, epoch_time)
	else:
		return (False, None)

def refresh_receipt(receipt):
	'''
		Verifies whether the bundleId is valid and whether there is at least one transactions in the receipt.
		Returns verification status (valid/invalid) and latest expiration date in case of any transaction or None otherwise
	'''
	
	# Receipt status check 
	status_valid = receipt[RECEIPT_KEY_STATUS] == RECEIPT_VALUE_STATUS_VALID

	if not status_valid:
		app.logger.debug('Receipt status NOT valid')
		return(False, None)

	# Bundle identifier check
	bundle_id_valid = receipt[RECEIPT_KEY_RECEIPT][RECEIPT_KEY_BUNDLE_ID] == APP_BUNDLE_ID

	if not bundle_id_valid:
		app.logger.debug('BundleId NOT valid')
		return (False, None)

	app.logger.debug('BundleId valid')

	epoch_time = 0
	
	if RECEIPT_KEY_LATEST_RECEIPT_INFO in receipt:
		latest_receipt_info = receipt[RECEIPT_KEY_LATEST_RECEIPT_INFO]
		for transaction in latest_receipt_info:
			transaction_epoch_ms = transaction[RECEIPT_KEY_EXPIRE_DATE_MS]
			epoch_time_tmp = float(transaction_epoch_ms) / 1000
			epoch_time = epoch_time_tmp if epoch_time_tmp > epoch_time else epoch_time

	if epoch_time > 0:
		return (True, epoch_time)
	else:
		return (False, None)



app.run(host='0.0.0.0')
