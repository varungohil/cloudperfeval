#ifndef SOCIAL_NETWORK_MICROSERVICES_TRACING_H
#define SOCIAL_NETWORK_MICROSERVICES_TRACING_H

#include <chrono>
#include <cstdlib>
#include <string>
#include <map>
#include <memory>
#include <yaml-cpp/yaml.h>
#include "logger.h"

#include "opentelemetry/context/propagation/global_propagator.h"
#include "opentelemetry/context/propagation/text_map_propagator.h"
#include "opentelemetry/exporters/ostream/span_exporter_factory.h"
#include <opentelemetry/exporters/otlp/otlp_http_exporter.h>
#include "opentelemetry/ext/http/client/http_client.h"
#include "opentelemetry/nostd/shared_ptr.h"
#include "opentelemetry/sdk/resource/resource.h"
#include "opentelemetry/sdk/trace/exporter.h"
#include "opentelemetry/sdk/trace/processor.h"
#include "opentelemetry/sdk/trace/tracer_provider_factory.h"
#include "opentelemetry/sdk/trace/batch_span_processor_factory.h"
#include "opentelemetry/sdk/trace/tracer_provider.h"
#include "opentelemetry/exporters/otlp/otlp_http.h"
#include "opentelemetry/sdk/trace/tracer_context.h"
#include "opentelemetry/sdk/trace/tracer_context_factory.h"
#include "opentelemetry/sdk/trace/tracer_provider_factory.h"
#include "opentelemetry/trace/propagation/http_trace_context.h"
#include "opentelemetry/trace/provider.h"
#include "opentelemetry/sdk/trace/samplers/always_on.h"


namespace social_network {

namespace nostd = opentelemetry::nostd;
namespace trace = opentelemetry::trace;
namespace context = opentelemetry::context;
namespace resource = opentelemetry::sdk::resource;
namespace sdktrace  = opentelemetry::sdk::trace;

template <typename T>
class HttpTextMapCarrier : public opentelemetry::context::propagation::TextMapCarrier
{
public:
  HttpTextMapCarrier(T &headers) : headers_(headers) {}
  HttpTextMapCarrier() = default;

  virtual opentelemetry::nostd::string_view Get(
      opentelemetry::nostd::string_view key) const noexcept override
  {
    // std::string key_to_compare = key.data();

    // auto it = headers_.find(key_to_compare);
    // if (it != headers_.end())
    // {
    //   return it->second;
    // }
    // return "";

    auto it = headers_.find(std::string(key));
    if (it != headers_.end()) {
        return opentelemetry::nostd::string_view(it->second);
    }
    return "";
  }

  virtual void Set(opentelemetry::nostd::string_view key,
                   opentelemetry::nostd::string_view value) noexcept override
  {
    // headers_.insert(std::pair<std::string, std::string>(std::string(key), std::string(value)));
    // if constexpr (!std::is_const<T>) {
    if constexpr (!std::is_const<typename std::remove_reference<T>::type>::value) {
      headers_[std::string(key)] = std::string(value);
    }
  }

  T& headers_;
};


inline void SetUpTracer(
    const std::string& config_file_path,
    const std::string& service) {
  auto configYAML = YAML::LoadFile(config_file_path);
  

  // Create resource with service name from parameter and config
  resource::ResourceAttributes resource_attributes = {
      {"service.name", service},
      {"service.namespace", "social_network"}
  };

  auto resource = resource::Resource::Create(resource_attributes);

  // Export to the local edge collector via the host-published OTLP port.
  // Swarm VIP routing to otel-collector:4318 adds multi-minute cross-node delay.
  // Prefer OTEL_EXPORTER_OTLP_TRACES_ENDPOINT; fall back to docker bridge IP
  // (host-gateway / extra_hosts) rather than the hostname alone.
  opentelemetry::exporter::otlp::OtlpHttpExporterOptions opts;
  if (const char *endpoint = std::getenv("OTEL_EXPORTER_OTLP_TRACES_ENDPOINT")) {
    opts.url = endpoint;
  } else {
    opts.url = "http://172.17.0.1:4318/v1/traces";
  }
  opts.content_type =
      opentelemetry::exporter::otlp::HttpRequestContentType::kBinary;
  opts.compression = "none";

  LOG(info) << service << " OTLP trace export URL: " << opts.url;

  auto exporter = std::unique_ptr<opentelemetry::sdk::trace::SpanExporter>(
      new opentelemetry::exporter::otlp::OtlpHttpExporter(opts));

  // BatchSpanProcessor; tune via OTEL_BSP_* env (see docker-compose-swarm.yml).
  sdktrace::BatchSpanProcessorOptions bsp_opts{};
  auto processor =
      sdktrace::BatchSpanProcessorFactory::Create(std::move(exporter), bsp_opts);

  std::vector<std::unique_ptr<opentelemetry::sdk::trace::SpanProcessor>> processors;
  processors.push_back(std::move(processor));
  

  // Head sampling disabled: emit every span so the collector's tail_sampling
  // processor can make the keep/drop decision on the complete trace.
  auto sampler = std::unique_ptr<opentelemetry::sdk::trace::AlwaysOnSampler>
      (new opentelemetry::sdk::trace::AlwaysOnSampler());

  std::unique_ptr<opentelemetry::sdk::trace::TracerContext> context =
      opentelemetry::sdk::trace::TracerContextFactory::Create(std::move(processors), resource, std::move(sampler));

  
  std::shared_ptr<opentelemetry::trace::TracerProvider> provider =
      opentelemetry::sdk::trace::TracerProviderFactory::Create(std::move(context));
  // Set the global trace provider
  opentelemetry::trace::Provider::SetTracerProvider(provider);

  // set global propagator
  opentelemetry::context::propagation::GlobalTextMapPropagator::SetGlobalPropagator(
      opentelemetry::nostd::shared_ptr<opentelemetry::context::propagation::TextMapPropagator>(
          new opentelemetry::trace::propagation::HttpTraceContext()));

}

// Push queued BatchSpanProcessor spans to the local collector before RPC return.
inline void FlushTraces() {
  auto provider = trace::Provider::GetTracerProvider();
  if (!provider) {
    return;
  }
  if (auto *sdk = dynamic_cast<sdktrace::TracerProvider *>(provider.get())) {
    sdk->ForceFlush(std::chrono::milliseconds(5000));
  }
}

opentelemetry::nostd::shared_ptr<opentelemetry::trace::Tracer> get_tracer(std::string tracer_name)
{
  auto provider = opentelemetry::trace::Provider::GetTracerProvider();
  return provider->GetTracer(tracer_name);
}


} // namespace social_network

#endif // SOCIAL_NETWORK_MICROSERVICES_TRACING_H
