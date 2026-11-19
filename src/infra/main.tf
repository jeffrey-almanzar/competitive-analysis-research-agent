# Terraform configuration for deploying the application on AWS.

provider "aws" {
  region = "us-west-2"
}

resource "aws_ecs_cluster" "main" {}

resource "aws_ecs_task_definition" "app" {
  # Task definition details
}

resource "aws_rds_instance" "db" {
  # Database configuration
}