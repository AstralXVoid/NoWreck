// models.h — the model types, defined inline (the header is the unit).

#ifndef PURE_CPP_MODELS_H
#define PURE_CPP_MODELS_H

#include <string>

namespace purecpp
{
    using Id = long;

    enum class Status
    {
        Active,
        Inactive
    };

    std::string escape(const std::string& text)
    {
        return text;
    }

    class User
    {
    public:
        User(Id id, const std::string& name) : id_(id), name_(name) {}

        virtual ~User() {}

        virtual std::string display() const
        {
            return name_;
        }

        std::string toJson() const
        {
            return "{\"name\":\"" + escape(display()) + "\"}";
        }

    private:
        Id id_;
        std::string name_;
    };

    class AdminUser : public User
    {
    public:
        AdminUser(Id id, const std::string& name, bool root) : User(id, name), root_(root)
        {
        }

        std::string display() const override
        {
            return User::display() + " (admin)";
        }

    private:
        bool root_;
    };
}

#endif
