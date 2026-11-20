variable "region" {
  description = "AWS region. This account's organization policy only allows us-east-2."
  type        = string
  default     = "us-east-2"
}

variable "allowed_cidrs" {
  description = "Only these addresses can reach the load balancer (e.g. [\"1.2.3.4/32\"]). The app has no login."
  type        = list(string)
}

variable "image_tag" {
  description = "Tag of the api and web images in ECR."
  type        = string
}

variable "anthropic_api_key" {
  type      = string
  sensitive = true
}

variable "exa_api_key" {
  type      = string
  sensitive = true
}

variable "default_model" {
  description = "Claude model used when a request doesn't pick one."
  type        = string
  default     = "claude-haiku-5-5"
}

variable "db_instance_class" {
  type    = string
  default = "db.t4g.micro"
}

variable "budget_email" {
  description = "If set, creates a monthly cost budget that emails this address at 50% and 100%."
  type        = string
  default     = ""
}

variable "budget_usd" {
  type    = number
  default = 25
}
