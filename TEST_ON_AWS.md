# Test Palvi Agrico Bot on AWS (EC2 + ngrok)

Complete step-by-step guide to run and test the bot on AWS without production deployment.

---

## Step 1: Create DynamoDB Tables

Go to AWS Console → DynamoDB → Create table (do this 3 times):

### Table 1: palvi-sessions
- Table name: `palvi-sessions`
- Partition key: `call_sid` (String)
- Settings: Default
- Create table
- After creation: Additional settings → TTL → Turn on → attribute: `ttl`

### Table 2: palvi-memory
- Table name: `palvi-memory`
- Partition key: `user_id` (String)
- Sort key: `memory_key` (String)
- Settings: Default
- Create table
- TTL → Turn on → attribute: `ttl`

### Table 3: palvi-orders
- Table name: `palvi-orders`
- Partition key: `order_id` (String)
- Settings: Default
- Create table

---

## Step 2: Create S3 Bucket

1. AWS Console → S3 → Create bucket
2. Bucket name: `palvi-knowledge-base`
3. Region: us-east-1
4. Keep all defaults
5. Create bucket

---

## Step 3: Enable Claude Sonnet in Bedrock

1. AWS Console → Amazon Bedrock → Model access
2. Click "Manage model access"
3. Find "Anthropic Claude 3.5 Sonnet v2"
4. Check the box → Request access
5. Wait for "Access granted" (usually instant)

---

## Step 4: Launch EC2 Instance

1. AWS Console → EC2 → Launch instances
2. Configure:
   - Name: `palvi-bot-test`
   - AMI: **Amazon Linux 2023** (default, free tier eligible)
   - Instance type: **t3.micro** (free tier) or t3.small (if you want more RAM)
   - Key pair: Click "Create new key pair"
     - Name: `palvi-key`
     - Type: RSA
     - Format: .pem
     - Download and save the .pem file
   - Network settings → Edit:
     - Allow SSH from: My IP
     - Add rule: Custom TCP, Port 8000, Source: 0.0.0.0/0
     - Add rule: Custom TCP, Port 443, Source: 0.0.0.0/0
   - Storage: 20 GB gp3
3. Click **Launch instance**
4. Wait until "Instance state" = Running
5. Copy the **Public IPv4 address** (e.g., 54.123.45.67)

---

## Step 5: Create IAM Role for EC2

The EC2 needs permissions to access DynamoDB, S3, Bedrock.

1. AWS Console → IAM → Roles → Create role
2. Trusted entity: **AWS service** → **EC2**
3. Add permissions:
   - `AmazonDynamoDBFullAccess`
   - `AmazonS3ReadOnlyAccess`
   - `AmazonBedrockFullAccess`
4. Role name: `palvi-ec2-role`
5. Create role

### Attach role to EC2:
1. EC2 Console → Select your instance
2. Actions → Security → Modify IAM role
3. Select `palvi-ec2-role`
4. Update IAM role

---

## Step 6: SSH into EC2

Open terminal (or use PuTTY on Windows):

```bash
# On Mac/Linux:
chmod 400 palvi-key.pem
ssh -i palvi-key.pem ec2-user@54.123.45.67

# On Windows (PowerShell):
ssh -i palvi-key.pem ec2-user@54.123.45.67
```

Replace `54.123.45.67` with your EC2's public IP.

---

## Step 7: Install Dependencies on EC2

Run these commands one by one after SSH:

```bash
# Update system
sudo dnf update -y

# Install Python 3.12
sudo dnf install python3.12 python3.12-pip git -y

# Verify
python3.12 --version
```

---

## Step 8: Upload Code to EC2

### Option A: Git clone (if you pushed to repo)
```bash
git clone https://github.com/YOUR_USERNAME/palvi-agrico-bot.git
cd palvi-agrico-bot
```

### Option B: SCP upload from your machine
Open a NEW terminal on your local machine:
```bash
# From your local machine (not EC2):
scp -i palvi-key.pem -r "C:\Users\sagar.lad\Desktop\AI Agent\palvi-agrico-bot" ec2-user@54.123.45.67:~/
```

Then back on EC2:
```bash
cd ~/palvi-agrico-bot
```

---

## Step 9: Install Python Packages

```bash
cd ~/palvi-agrico-bot
python3.12 -m pip install -r requirements.txt
```

If you get permission errors:
```bash
python3.12 -m pip install --user -r requirements.txt
```

---

## Step 10: Create .env File

```bash
cp .env.example .env
nano .env
```

Fill in your values:
```
TWILIO_ACCOUNT_SID=AC6dd8426f15cb5056732206d6d2c9013f
TWILIO_AUTH_TOKEN=YOUR_NEW_AUTH_TOKEN
TWILIO_FROM_NUMBER=+14243737052

SARVAM_API_KEY=YOUR_SARVAM_API_KEY
SARVAM_STT_URL=https://api.sarvam.ai/speech-to-text
SARVAM_TTS_URL=https://api.sarvam.ai/text-to-speech

AWS_REGION=us-east-1
DYNAMODB_SESSION_TABLE=palvi-sessions
DYNAMODB_MEMORY_TABLE=palvi-memory
DYNAMODB_ORDER_TABLE=palvi-orders
S3_KNOWLEDGE_BUCKET=palvi-knowledge-base
OPENSEARCH_ENDPOINT=
BEDROCK_MODEL_ID=anthropic.claude-3-5-sonnet-20241022-v2:0

APP_HOST=0.0.0.0
APP_PORT=8000
BASE_URL=https://YOUR_NGROK_URL
```

Save: Ctrl+O → Enter → Ctrl+X

(Leave BASE_URL blank for now — you'll update it after ngrok in Step 12)

---

## Step 11: Start the Bot Server

```bash
cd ~/palvi-agrico-bot
python3.12 -m uvicorn app.main:app --host 0.0.0.0 --port 8000
```

You should see:
```
INFO:     Started server process
INFO:     Waiting for application startup.
INFO:     Application startup complete.
INFO:     Uvicorn running on http://0.0.0.0:8000
```

Test health check (open new terminal → SSH again):
```bash
curl http://localhost:8000/health
```

Should return: `{"status":"healthy","service":"palvi-agrico-bot"}`

---

## Step 12: Install and Run ngrok

Open a **second SSH session** to the same EC2 (keep the bot running in first):

```bash
# Install ngrok
curl -sSL https://ngrok-agent.s3.amazonaws.com/ngrok-v3-stable-linux-amd64.tgz | sudo tar xz -C /usr/local/bin

# Sign up at https://ngrok.com (free) and get your auth token
# Then authenticate:
ngrok config add-authtoken YOUR_NGROK_AUTH_TOKEN

# Start tunnel
ngrok http 8000
```

ngrok will show something like:
```
Forwarding    https://a1b2c3d4.ngrok-free.app -> http://localhost:8000
```

**Copy the https URL** (e.g., `https://a1b2c3d4.ngrok-free.app`)

---

## Step 13: Update .env with ngrok URL

In the first SSH session, stop the bot (Ctrl+C), then:

```bash
nano .env
```

Update the `BASE_URL` line:
```
BASE_URL=https://a1b2c3d4.ngrok-free.app
```

Save and restart the bot:
```bash
python3.12 -m uvicorn app.main:app --host 0.0.0.0 --port 8000
```

---

## Step 14: Configure Twilio Webhook

1. Go to https://console.twilio.com
2. Phone Numbers → Manage → Active numbers → Click your number (+14243737052)
3. Voice Configuration:
   - "A call comes in" → Webhook
   - URL: `https://a1b2c3d4.ngrok-free.app/voice/incoming`
   - Method: POST
4. Click Save

---

## Step 15: Test with a Phone Call

### Test 1: Call your Twilio number
- Dial +14243737052 from your phone
- You should hear the Marathi greeting from Sarvam TTS

### Test 2: Trigger outbound call
From the second SSH session:
```bash
curl -X POST http://localhost:8000/call/initiate \
  -H "Content-Type: application/json" \
  -d '{"phone_number": "7066498822"}'
```

### Test 3: Check health
```bash
curl https://a1b2c3d4.ngrok-free.app/health
```

---

## Step 16: Monitor Logs

The bot logs everything to the terminal where uvicorn is running:
```
[SARVAM STT] 'सोयाबीन 5 एकर'
[GRAPH] Step=ask_crop, Input='सोयाबीन 5 एकर'
[BEDROCK] Reply: 'सर, तुमच्या सोयाबीन पिकासाठी...'
[SARVAM TTS] Generated audio for: 'सर, तुमच्या...'
```

---

## Troubleshooting

### "Connection refused" on curl
- Bot isn't running. Check the first terminal.

### ngrok shows "ERR_NGROK_6022"
- Free ngrok has session limits. Restart ngrok.

### Twilio says "Application error"
- Check bot logs for errors
- Verify .env has correct values
- Ensure EC2 IAM role has Bedrock/DynamoDB access

### Sarvam returns empty
- Check API key is correct
- Free tier may have rate limits (check Sarvam dashboard)

### Bot doesn't respond
- Check ngrok is running and URL matches Twilio config
- Check EC2 security group allows port 8000

---

## Stop Everything

When done testing:
```bash
# Stop bot (Ctrl+C in first terminal)
# Stop ngrok (Ctrl+C in second terminal)

# Optionally stop EC2 to save cost:
# EC2 Console → Select instance → Instance state → Stop instance
```

---

## Cost

- EC2 t3.micro: Free tier (or ~$0.01/hr if not free tier)
- DynamoDB: Free tier (25 GB + 25 RCU/WCU)
- Bedrock Claude: ~$0.003 per call turn
- Sarvam: Free tier
- ngrok: Free
- **Total for testing: ~$0-1/day**
