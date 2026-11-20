output "url" {
  description = "Open this in your browser (reachable only from allowed_cidrs)."
  value       = "http://${aws_lb.web.dns_name}"
}

output "region" {
  value = var.region
}

output "cluster" {
  value = aws_ecs_cluster.main.name
}

output "api_repository" {
  value = aws_ecr_repository.api.repository_url
}

output "web_repository" {
  value = aws_ecr_repository.web.repository_url
}

output "api_url_internal" {
  value = local.api_url
}
