# AWS Production Deployment Guide

This guide provides step-by-step instructions for deploying the TrueQuery Advanced RAG System to AWS from scratch. Use this guide if you need to recreate the production environment for an interview demonstration.

---

## Step 1: Create the IAM Deployment User
This step creates an AWS identity that allows GitHub Actions to securely push Docker images into your AWS account.

1. Go to the AWS Console and search for **IAM**.
2. Click **Users** on the left menu, then click **Create user**.
3. Name the user `github-actions-deployer` and click Next.
4. Select **Attach policies directly**.
5. Search for and check **`AmazonEC2ContainerRegistryPowerUser`**. Click Next and create the user.
6. Click on the newly created user, go to the **Security credentials** tab, and click **Create access key**.
7. Select **Third-party service**, check the box, and click Next.
8. **CRITICAL:** Copy the **Access Key ID** and **Secret Access Key** and save them temporarily. You will need them for Step 4.

## Step 2: Create the Container Registry (ECR)
This creates the cloud storage bin where your built Docker images will be hosted.

1. In the AWS Console, search for **ECR** (Elastic Container Registry).
2. Click **Create repository**.
3. Set the visibility to **Private**.
4. Name the repository exactly: `advance-rag-app` (This must exactly match the `ECR_REPOSITORY` variable in your `.github/workflows/deploy.yml` file).
5. Leave all other settings as default and click **Create repository**.

## Step 3: Provision the EC2 Server
This spins up the actual cloud computer that will host your website.

1. In the AWS Console, search for **EC2** and click **Launch instance**.
2. **Name:** `RAG-Production-Server`.
3. **OS Images:** Select **Ubuntu** (24.04 or 22.04 LTS).
4. **Instance Type:** Select **t3.small** (2 vCPU, 2 GiB Memory). *Do not use t3.micro, as Docker and the AI models require more than 1 GiB of RAM.*
5. **Key pair:** Click "Create new key pair", name it `rag-key`, and download the `.pem` file to your computer.
6. **Network settings:** Check all three boxes:
   - Allow SSH traffic
   - Allow HTTPS traffic from the internet
   - Allow HTTP traffic from the internet
7. **Configure storage:** Expand this section and change the disk size from `8` to **`30`** GiB (this maximizes your Free Tier allowance and prevents Docker out-of-storage crashes).
8. Click **Launch instance**.

## Step 4: Configure GitHub Secrets
This securely connects your GitHub repository to your AWS account.

1. Go to your GitHub repository -> **Settings** -> **Secrets and variables** -> **Actions**.
2. Click **New repository secret** and add the following four secrets:
   - `AWS_ACCESS_KEY_ID`: *(Paste the Access Key from Step 1)*
   - `AWS_SECRET_ACCESS_KEY`: *(Paste the Secret Key from Step 1)*
   - `EC2_HOST`: *(Paste the Public IPv4 address of your new EC2 instance)*
   - `EC2_SSH_KEY`: *(Open your downloaded `rag-key.pem` file in Notepad, copy the ENTIRE text including `-----BEGIN RSA PRIVATE KEY-----` and `-----END RSA PRIVATE KEY-----`, and paste it here)*

## Step 5: Prepare the EC2 Server
This installs Docker and injects your secret API keys into the server.

1. Go to the EC2 Dashboard in the AWS Console, select your server, click **Connect**, and use **EC2 Instance Connect** to open a browser terminal.
2. Install Docker by copying and pasting this entire block:
   ```bash
   sudo apt-get update
   sudo apt-get install -y docker.io awscli
   sudo usermod -aG docker ubuntu
   newgrp docker
   ```
3. Create your production secrets file:
   ```bash
   nano /home/ubuntu/.env
   ```
4. Paste your API keys into the nano editor. Ensure they are formatted like your local `.env`:
   ```env
   GOOGLE_API_KEY=your_key_here
   QDRANT_URL=your_qdrant_url
   QDRANT_API_KEY=your_qdrant_key
   UNSTRUCTURED_API_KEY=your_unstructured_key
   UNSTRUCTURED_API_URL=your_unstructured_url
   DEEPEVAL_TELEMETRY=0
   ```
5. Press **Ctrl+X**, then **Y**, then **Enter** to save and exit nano.
6. Type `exit` to close the terminal.

## Step 6: Trigger the Deployment
Everything is now wired together. The CI/CD pipeline defined in `.github/workflows/deploy.yml` will now work automatically.

1. Make a small code change locally, or create an empty commit:
   ```bash
   git commit --allow-empty -m "Trigger production deployment"
   git push origin main
   ```
2. Go to the **Actions** tab on GitHub to watch the pipeline run.
3. Once it turns green, type your EC2 Public IP address into your browser to view your live, production-ready Advanced RAG application!
